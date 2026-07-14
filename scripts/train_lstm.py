"""
train_lstm.py — LSTM for satellite GHI ratio correction.

Architecture: seq2one — 8 timesteps (24h @ 3-hourly) → ratio [0, 3].
Comparison vs XGBoost baseline via grouped 5-fold CV.
"""
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error
import sys, os, time, argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from scripts.retrain_unified import load_db_nasa, load_zindi, FEATURES, y_ratio, make_model, fit_model

SEQ_LEN = 8
BATCH_SIZE = 256
EPOCHS = 40
LR = 1e-3
HIDDEN_SIZE = 64

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class SeqDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y).unsqueeze(1)
    def __len__(self):
        return len(self.X)
    def __getitem__(self, i):
        return self.X[i], self.y[i]


class LSTMModel(nn.Module):
    def __init__(self, n_features):
        super().__init__()
        self.lstm = nn.LSTM(n_features, HIDDEN_SIZE, 1, batch_first=True, bidirectional=True)
        self.fc = nn.Sequential(
            nn.Linear(HIDDEN_SIZE * 2, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 1),
        )
    def forward(self, x):
        _, (h, _) = self.lstm(x)
        h = torch.cat([h[-2], h[-1]], dim=1)
        return torch.sigmoid(self.fc(h)) * 3.0


def make_sequences(df, features, seq_len=SEQ_LEN):
    """Create sliding-window sequences, returning (X, y, original_indices)."""
    groups = df["group"]
    seqs, tgts, orig_idx = [], [], []
    for g in groups.unique():
        gdf = df[groups == g].sort_values("timestamp")
        X = gdf[features].values.astype(np.float32)
        y = y_ratio(gdf["ghi_ground"].values, gdf["ghi_satellite"].values).astype(np.float32)
        g_idx = gdf.index.values
        if len(X) < seq_len:
            continue
        for i in range(len(X) - seq_len + 1):
            seqs.append(X[i : i + seq_len])
            tgts.append(y[i + seq_len - 1])
            orig_idx.append(g_idx[i + seq_len - 1])
    return np.array(seqs), np.array(tgts), np.array(orig_idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kfold", type=int, default=5)
    ap.add_argument("--seq-len", type=int, default=SEQ_LEN)
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    args = ap.parse_args()

    print(f"LSTM — seq_len={args.seq_len}, epochs={args.epochs}, hidden={HIDDEN_SIZE}, device={device}\n")

    dfs = []
    d = load_db_nasa()
    if not d.empty: dfs.append(d)
    z = load_zindi()
    if not z.empty: dfs.append(z)
    df = pd.concat(dfs, ignore_index=True)
    for f in FEATURES + ["ghi_ground", "dni_ground", "group", "source_weight", "clear_sky_ghi"]:
        if f not in df.columns: df[f] = 0.0
    df.dropna(subset=FEATURES + ["ghi_ground", "dni_ground"], inplace=True)
    df = df[(df["ghi_satellite"] > 0) | (df["ghi_ground"] > 0)].copy()
    raw_rmse = np.sqrt(((df["ghi_ground"] - df["ghi_satellite"]) ** 2).mean())
    print(f"Data: {len(df)} records, {df['group'].nunique()} groups  |  Raw NASA RMSE: {raw_rmse:.2f}\n")

    gkf = GroupKFold(n_splits=args.kfold)

    # === XGBoost baseline ===
    print("--- XGBoost Baseline ---")
    xgb_rmses = []
    for ti, vi in gkf.split(df, y=df["ghi_ground"] - df["ghi_satellite"], groups=df["group"]):
        tr, va = df.iloc[ti].copy(), df.iloc[vi].copy()
        tr["station_bias"] = 0.0; va["station_bias"] = 0.0
        m = make_model("xgboost")
        sw = tr.get("source_weight", pd.Series(1.0, index=tr.index)).values
        y_tr = y_ratio(tr["ghi_ground"].values, tr["ghi_satellite"].values)
        fit_model(m, tr[FEATURES], y_tr, sample_weight=sw)
        p = np.clip(m.predict(va[FEATURES]), 0.0, 3.0) * va["ghi_satellite"].values
        xgb_rmses.append(np.sqrt(mean_squared_error(va["ghi_ground"].values, p)))
    print(f"  XGBoost: {np.mean(xgb_rmses):.2f} ± {np.std(xgb_rmses):.2f}")
    for i, r in enumerate(xgb_rmses):
        print(f"    Fold {i+1}: {r:.2f}")

    # === LSTM ===
    print("\n--- LSTM ---")
    lstm_rmses, lstm_ratio_rmses = [], []
    fold_idx = 0
    for ti, vi in gkf.split(df, y=df["ghi_ground"] - df["ghi_satellite"], groups=df["group"]):
        fold_idx += 1
        tr, va = df.iloc[ti].copy(), df.iloc[vi].copy()
        tr["station_bias"] = 0.0; va["station_bias"] = 0.0

        X_tr, y_tr, _ = make_sequences(tr, FEATURES, args.seq_len)
        X_va, y_va, va_idx = make_sequences(va, FEATURES, args.seq_len)

        if len(X_tr) < 100 or len(X_va) < 10:
            print(f"  Fold {fold_idx}: too few sequences ({len(X_tr)}, {len(X_va)}), skipping")
            continue

        # Standardize per fold
        m = X_tr.mean(axis=(0, 1), keepdims=True)
        s = X_tr.std(axis=(0, 1), keepdims=True) + 1e-8
        X_tr = (X_tr - m) / s
        X_va = (X_va - m) / s

        tr_loader = DataLoader(SeqDataset(X_tr, y_tr), BATCH_SIZE, shuffle=True)
        va_loader = DataLoader(SeqDataset(X_va, y_va), BATCH_SIZE, shuffle=False)

        model = LSTMModel(n_features=len(FEATURES)).to(device)
        opt = optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
        sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min", factor=0.5, patience=4)
        crit = nn.MSELoss()

        t0 = time.time()
        best_val = float("inf")
        stale = 0
        for epoch in range(args.epochs):
            model.train()
            for Xb, yb in tr_loader:
                Xb, yb = Xb.to(device), yb.to(device)
                opt.zero_grad()
                crit(model(Xb), yb).backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()

            model.eval()
            with torch.no_grad():
                vloss = 0
                for Xb, yb in va_loader:
                    vloss += crit(model(Xb.to(device)), yb.to(device)).item() * len(Xb)
                vloss /= len(va_loader.dataset)
            sched.step(vloss)
            if vloss < best_val:
                best_val = vloss; stale = 0
            else:
                stale += 1
                if stale >= 8:
                    break

        # Evaluate on ratio
        model.eval()
        preds = []
        with torch.no_grad():
            for Xb, _ in va_loader:
                preds.append(model(Xb.to(device)).cpu().numpy())
        pred_ratio = np.clip(np.concatenate(preds).ravel(), 0.0, 3.0)

        # Map back to GHI space using tracked original indices
        va_map = va.loc[va_idx]
        ghi_pred = va_map["ghi_satellite"].values * pred_ratio
        fold_rmse = np.sqrt(mean_squared_error(va_map["ghi_ground"].values, ghi_pred))
        ratio_rmse = np.sqrt(np.mean((pred_ratio - y_va) ** 2))
        lstm_rmses.append(fold_rmse)
        lstm_ratio_rmses.append(ratio_rmse)
        elapsed = time.time() - t0
        print(f"  Fold {fold_idx}: LSTM GHI RMSE = {fold_rmse:.2f}  (ratio RMSE: {ratio_rmse:.4f}, {elapsed:.0f}s, {epoch+1} epochs)")

    mean_lstm = np.mean(lstm_rmses) if lstm_rmses else 0
    std_lstm = np.std(lstm_rmses) if lstm_rmses else 0

    print(f"\n{'='*55}")
    print(f"  RESULTS (grouped {args.kfold}-fold CV)")
    print(f"{'='*55}")
    print(f"  Raw NASA:  {raw_rmse:.2f}")
    print(f"  XGBoost:   {np.mean(xgb_rmses):.2f} ± {np.std(xgb_rmses):.2f}")
    print(f"  LSTM:      {mean_lstm:.2f} ± {std_lstm:.2f}")
    print(f"  LSTM Δ vs XGBoost: {np.mean(xgb_rmses) - mean_lstm:+.2f}")


if __name__ == "__main__":
    main()
