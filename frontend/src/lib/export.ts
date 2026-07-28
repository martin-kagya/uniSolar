/**
 * export.ts
 *
 * Export utilities for the UNISOLAR report.
 * PDF reports are built programmatically with jsPDF — no html2canvas.
 * PNG map exports still use html2canvas.
 */

import { downloadBlob } from './download';

// ---------- Helpers ----------

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function formatGHS(v: number): string {
  if (v == null || !Number.isFinite(v)) return 'N/A';
  return `GH\u20B3${Math.round(v).toLocaleString()}`;
}

function formatEnergy(kwh: number | null | undefined): string {
  if (kwh == null || !Number.isFinite(kwh) || kwh === 0) return '0 kWh';
  if (kwh >= 10000) return `${(kwh / 1000).toFixed(1)} MWh`;
  return `${Math.round(kwh).toLocaleString()} kWh`;
}

// ---------- PDF Report ----------

export interface ReportData {
  annualEnergy?: number;
  capacityKw?: number;
  panelCount?: number;
  npv?: number;
  payback?: number;
  irr?: number | null;
  lcoe?: number | null;
  capex?: number | null;
  lifetimeSavings?: number | null;
  monthlyEnergy?: number[];
  losses?: Record<string, number>;
  lossParams?: Record<string, number>;
  environmentalMetrics?: {
    mean_pm25?: number | null;
    mean_pm10?: number | null;
    pm_data_available?: boolean;
    mean_cleaning_events_monthly?: number;
  };
  financials?: {
    debt?: {
      debt_amount?: number;
      equity_amount?: number;
      annual_debt_service?: number;
      min_dscr?: number;
      dscr_by_year?: number[];
      debt_ratio_pct?: number;
      interest_rate_pct?: number;
      loan_term_years?: number;
    };
    om_breakdown?: {
      cleaning?: number;
      inverter_reserve?: number;
      monitoring?: number;
      insurance?: number;
      spare_parts?: number;
    };
    om_per_kw?: number;
  };
  probabilisticResults?: {
    p50_yield?: number;
    p90_yield?: number;
    p99_yield?: number;
    p50_npv?: number;
    p90_npv?: number;
    p99_npv?: number;
    energy_p50_kwh?: number;
    energy_p90_kwh?: number;
    energy_p99_kwh?: number;
    uncertainty_breakdown?: {
      model_cov?: number;
      interannual_cov?: number;
      total_cov?: number;
      p90_over_p50?: number;
    };
    p90_calibration?: Record<string, number>;
  };
}

export async function generateReportPDF(data: ReportData, filename = 'UniSolar_Report'): Promise<void> {
  const { default: jsPDF } = await import('jspdf');
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  const W = 210;
  const H = 297;
  const LM = 18;
  const RM = W - 18;
  const CW = RM - LM;
  const GOLD = [245, 158, 11] as const;
  const GREEN = [16, 185, 129] as const;
  const RED = [239, 68, 68] as const;
  const DARK = [30, 30, 30] as const;
  const DIM = [120, 120, 120] as const;
  const WHITE = [255, 255, 255] as const;
  const LIGHT_BG = [245, 245, 245] as const;

  let y = 0;

  function checkPage(need = 30) {
    if (y + need > H - 25) { pdf.addPage(); y = 20; }
  }

  function goldBar() {
    pdf.setFillColor(...GOLD);
    pdf.rect(LM, y, CW, 0.6, 'F');
    y += 4;
  }

  function sectionTitle(title: string) {
    checkPage(18);
    y += 4;
    pdf.setFontSize(13);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text(title, LM, y);
    y += 4;
    goldBar();
  }

  function subLabel(label: string, value: string, x: number, wide = 55) {
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'normal');
    pdf.text(label.toUpperCase(), x, y);
    pdf.setFontSize(11);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text(value, x, y + 5);
  }

  function textRow(label: string, value: string, indent = LM) {
    checkPage(6);
    pdf.setFontSize(8);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'normal');
    pdf.text(label, indent, y);
    pdf.setFontSize(8);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text(value, RM, y, { align: 'right' });
    y += 4.5;
  }

  // ── PAGE 1: Header + Yield ──
  // Header
  pdf.setFillColor(18, 18, 18);
  pdf.rect(0, 0, W, 38, 'F');
  pdf.setFontSize(22);
  pdf.setTextColor(...GOLD);
  pdf.setFont('helvetica', 'bold');
  pdf.text('UNISOLAR', LM, 18);
  pdf.setFontSize(9);
  pdf.setTextColor(200, 200, 200);
  pdf.setFont('helvetica', 'normal');
  pdf.text('Financial & Yield Audit Report', LM, 25);
  pdf.setFontSize(7);
  pdf.setTextColor(150, 150, 150);
  pdf.text(`Generated ${new Date().toLocaleDateString('en-GB')} ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`, LM, 31);

  y = 48;

  // Yield Summary
  sectionTitle('Yield Summary');
  const y0 = y;
  const cardW = (CW - 12) / 3;
  const cards = [
    { label: 'Annual Energy', value: formatEnergy(data.annualEnergy) },
    { label: 'Installed DC', value: `${(data.capacityKw ?? 0).toFixed(1)} kWp` },
    { label: 'Panel Count', value: `${data.panelCount ?? 0}` },
  ];
  cards.forEach((c, i) => {
    const cx = LM + i * (cardW + 6);
    pdf.setFillColor(...LIGHT_BG);
    pdf.roundedRect(cx, y0, cardW, 16, 2, 2, 'F');
    subLabel(c.label, c.value, cx + 4, cardW - 8);
  });
  y = y0 + 22;

  // Probabilistic
  if (data.probabilisticResults) {
    const pr = data.probabilisticResults;
    checkPage(18);
    pdf.setFontSize(9);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Yield Probability Distribution (1,000 Monte Carlo runs)', LM, y);
    y += 5;
    const bx = LM;
    const bw = 52;
    const gap = 5;
    // P50
    pdf.setFillColor(240, 240, 240);
    pdf.roundedRect(bx, y, bw, 10, 1.5, 1.5, 'F');
    subLabel('P50 (Expected)', formatEnergy(pr.p50_yield), bx + 3, bw - 6);
    // P90
    pdf.setFillColor(232, 252, 244);
    pdf.roundedRect(bx + bw + gap, y, bw, 10, 1.5, 1.5, 'F');
    subLabel('P90 (Bankable)', formatEnergy(pr.p90_yield), bx + bw + gap + 3, bw - 6);
    // P99
    if (pr.p99_yield != null) {
      pdf.setFillColor(254, 249, 231);
      pdf.roundedRect(bx + 2 * (bw + gap), y, bw, 10, 1.5, 1.5, 'F');
      subLabel('P99 (Worst-case)', formatEnergy(pr.p99_yield), bx + 2 * (bw + gap) + 3, bw - 6);
    }
    // NPV annotations
    y += 13;
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    if (pr.p50_npv != null) pdf.text(`P50 NPV: ${formatGHS(pr.p50_npv)}`, bx + 3, y);
    if (pr.p90_npv != null) pdf.text(`P90 NPV: ${formatGHS(pr.p90_npv)}`, bx + bw + gap + 3, y);
    if (pr.p99_npv != null) pdf.text(`P99 NPV: ${formatGHS(pr.p99_npv)}`, bx + 2 * (bw + gap) + 3, y);
    y += 6;
    // Calibration provenance (the defensible bit)
    const cov = pr.p90_calibration?.['0.90'];
    if (cov != null) {
      pdf.setFontSize(7);
      pdf.setTextColor(...DIM);
      pdf.text(`Resource P90 calibrated: ${(cov * 100).toFixed(1)}% empirical coverage (conformal, leave-one-station-out).`, bx, y);
      y += 6;
    }
  }

  // Monthly Yield Bar Chart
  if (data.monthlyEnergy && data.monthlyEnergy.length === 12) {
    checkPage(70);
    pdf.setFontSize(9);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Monthly Yield Forecast (kWh)', LM, y);
    y += 5;
    const maxVal = Math.max(...data.monthlyEnergy, 1);
    const chartH = 40;
    const barW = (CW - 12) / 12;
    data.monthlyEnergy.forEach((v, i) => {
      const bx = LM + i * barW + 1;
      const bh = (v / maxVal) * chartH;
      // bar
      pdf.setFillColor(245, 158, 11);
      pdf.roundedRect(bx, y + chartH - bh, barW - 2, bh, 0.8, 0.8, 'F');
      // value on top
      pdf.setFontSize(5);
      pdf.setTextColor(...DARK);
      pdf.setFont('helvetica', 'normal');
      const valStr = v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${Math.round(v)}`;
      pdf.text(valStr, bx + (barW - 2) / 2, y + chartH - bh - 1.2, { align: 'center' });
      // month label
      pdf.setFontSize(6);
      pdf.setTextColor(...DIM);
      pdf.text(MONTHS[i], bx + (barW - 2) / 2, y + chartH + 4, { align: 'center' });
    });
    y += chartH + 10;
  }

  // Loss Breakdown
  const lossKeys = ['soiling', 'shading', 'degradation', 'inverter', 'physics_derate'] as const;
  const lossLabels: Record<string, string> = { soiling: 'Soiling', shading: 'Shading', degradation: 'Degradation', inverter: 'Inverter Efficiency', physics_derate: 'Wiring / LID / Mismatch' };
  const lossColors: Record<string, [number, number, number]> = { soiling: [245, 158, 11], shading: [139, 92, 246], degradation: [239, 68, 68], inverter: [6, 182, 212], physics_derate: [100, 116, 139] };

  const lossRows = lossKeys
    .filter(k => (data.losses?.[`${k}_percent`] ?? 0) > 0.01)
    .map(k => ({ key: k, label: lossLabels[k], value: data.losses![`${k}_percent`]! }));

  if (lossRows.length > 0) {
    sectionTitle('Loss Waterfall');
    const barMax = Math.max(...lossRows.map(r => r.value), 1);
    const barMaxW = CW - 60;
    lossRows.forEach(r => {
      checkPage(6);
      pdf.setFontSize(7);
      pdf.setTextColor(...DARK);
      pdf.setFont('helvetica', 'normal');
      pdf.text(r.label, LM, y + 3);
      // bar
      const bw = (r.value / barMax) * barMaxW;
      const c = lossColors[r.key] ?? DIM;
      pdf.setFillColor(...c);
      pdf.roundedRect(LM + 48, y, bw, 4.5, 0.8, 0.8, 'F');
      // value
      pdf.setFontSize(7);
      pdf.setTextColor(...DARK);
      pdf.setFont('helvetica', 'bold');
      pdf.text(`${r.value.toFixed(1)}%`, LM + 52 + bw, y + 3.5);
      y += 7;
    });
    const totalLoss = lossRows.reduce((s, r) => s + r.value, 0);
    y += 1;
    textRow('Total Loss', `${totalLoss.toFixed(1)}%`);
    y += 2;
  }

  // Key Assumptions
  sectionTitle('Key Assumptions');
  const lp = data.lossParams ?? {};
  const invEff = lp.actual_inverter_efficiency_pct ?? lp.inverter_efficiency_pct ?? 96;
  const assumptions: [string, string][] = [
    ['Degradation Rate', `${(lp.degradation_rate_pct ?? 0.5).toFixed(1)}%/yr`],
    ['Soiling Loss', `${(lp.soiling_rate_pct ?? 5.0).toFixed(1)}% (annual avg)`],
    ['Discount Rate (WACC)', '8.0%'],
    ['Tariff Escalation', '3.0%/yr'],
    ['O&M Escalation', '2.0%/yr'],
    ['System Lifetime', '25 years'],
    ['Inverter Efficiency', `${invEff.toFixed(1)}%`],
    ['Wiring Loss', `${(lp.wiring_loss_pct ?? 2).toFixed(1)}%`],
    ['LID Loss', `${(lp.lid_loss_pct ?? 2).toFixed(1)}%`],
    ['Mismatch Loss', `${(lp.mismatch_loss_pct ?? 2).toFixed(1)}%`],
    ['DC/AC Ratio', '~1.2 (module-dependent)'],
  ];
  const colW = CW / 3;
  assumptions.forEach(([k, v], i) => {
    checkPage(5);
    const col = i % 3;
    const row = Math.floor(i / 3);
    const cx = LM + col * colW;
    const cy = y + row * 7;
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'normal');
    pdf.text(k, cx, cy);
    pdf.setFontSize(7);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text(v, cx + colW - 2, cy, { align: 'right' });
  });
  y += Math.ceil(assumptions.length / 3) * 7 + 4;

  // ── PAGE 2: Financial ──
  pdf.addPage();
  y = 20;

  sectionTitle('Financial Summary');
  y += 1;
  const fCards = [
    { label: 'Net Present Value', value: formatGHS(data.npv) },
    { label: 'Payback Period', value: data.payback != null ? `${data.payback.toFixed(1)} Years` : 'N/A' },
    { label: 'Internal Rate of Return', value: data.irr != null ? `${(data.irr * 100).toFixed(1)}%` : 'N/A' },
  ];
  const fCardW = (CW - 12) / 3;
  fCards.forEach((c, i) => {
    const cx = LM + i * (fCardW + 6);
    pdf.setFillColor(...LIGHT_BG);
    pdf.roundedRect(cx, y, fCardW, 16, 2, 2, 'F');
    subLabel(c.label, c.value, cx + 4, fCardW - 8);
  });
  y += 22;

  // LCOE / CAPEX / Lifetime Savings
  const sCards = [
    { label: 'LCOE', value: data.lcoe != null ? `GH\u20B3${data.lcoe.toFixed(2)}/kWh` : 'N/A' },
    { label: 'Total CAPEX', value: formatGHS(data.capex) },
    { label: 'Lifetime Savings', value: formatGHS(data.lifetimeSavings) },
  ];
  sCards.forEach((c, i) => {
    const cx = LM + i * (fCardW + 6);
    pdf.setFillColor(...LIGHT_BG);
    pdf.roundedRect(cx, y, fCardW, 16, 2, 2, 'F');
    subLabel(c.label, c.value, cx + 4, fCardW - 8);
  });
  y += 22;

  // Monthly Savings Bar Chart
  if (data.monthlyEnergy && data.monthlyEnergy.length === 12) {
    checkPage(55);
    const tariff = data.lossParams?.effective_tariff ?? 1.90;
    const savings = data.monthlyEnergy.map(v => v * tariff);
    const maxVal = Math.max(...savings, 1);
    const chartH = 38;
    const barW = (CW - 12) / 12;

    pdf.setFontSize(9);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'bold');
    pdf.text(`Projected Monthly Savings (GH\u20B3, tariff GH\u20B3${tariff.toFixed(2)}/kWh)`, LM, y);
    y += 5;

    savings.forEach((v, i) => {
      const bx = LM + i * barW + 1;
      const bh = (v / maxVal) * chartH;
      pdf.setFillColor(...GREEN);
      pdf.roundedRect(bx, y + chartH - bh, barW - 2, bh, 0.8, 0.8, 'F');
      pdf.setFontSize(5);
      pdf.setTextColor(...DARK);
      pdf.setFont('helvetica', 'normal');
      const valStr = v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${Math.round(v)}`;
      pdf.text(valStr, bx + (barW - 2) / 2, y + chartH - bh - 1.2, { align: 'center' });
      pdf.setFontSize(6);
      pdf.setTextColor(...DIM);
      pdf.text(MONTHS[i], bx + (barW - 2) / 2, y + chartH + 4, { align: 'center' });
    });
    y += chartH + 10;
  }

  // Financial Parameters table
  sectionTitle('Financial Parameters');
  const finParams: [string, string][] = [
    ['Installed DC', `${(data.capacityKw ?? 0).toFixed(1)} kWp`],
    ['LCOE', data.lcoe != null ? `GH\u20B3${data.lcoe.toFixed(2)}/kWh` : 'N/A'],
    ['Year-1 Savings', formatGHS(data.annualEnergy != null ? data.annualEnergy * (data.lossParams?.effective_tariff ?? 1.90) : null)],
    ['Tariff Mode', data.lossParams?.tariff_mode === 'ecg_official' ? 'ECG Official' : 'Flat Rate'],
  ];
  finParams.forEach(([k, v]) => textRow(k, v));
  y += 2;

  // ── DSCR ──
  const debt = data.financials?.debt;
  if (debt) {
    sectionTitle('Debt Service Coverage Ratio (DSCR)');
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`${(debt.debt_ratio_pct ?? 65).toFixed(0)}% debt at ${(debt.interest_rate_pct ?? 12).toFixed(0)}% interest over ${debt.loan_term_years ?? 10} years`, LM, y);
    y += 5;

    const dCards = [
      { label: 'Debt Amount', value: formatGHS(debt.debt_amount) },
      { label: 'Equity', value: formatGHS(debt.equity_amount) },
      { label: 'Annual Debt Service', value: formatGHS(debt.annual_debt_service) },
      { label: 'Min DSCR', value: debt.min_dscr != null ? `${debt.min_dscr.toFixed(2)}x` : 'N/A' },
    ];
    const dCardW = (CW - 18) / 4;
    dCards.forEach((c, i) => {
      const cx = LM + i * (dCardW + 6);
      pdf.setFillColor(...LIGHT_BG);
      pdf.roundedRect(cx, y, dCardW, 14, 2, 2, 'F');
      subLabel(c.label, c.value, cx + 3, dCardW - 6);
    });
    y += 20;

    // DSCR bar chart
    if (debt.dscr_by_year && debt.dscr_by_year.length > 0) {
      checkPage(35);
      const barH = 28;
      const barW = (CW - 20) / debt.dscr_by_year.length;
      const maxDscr = Math.max(...debt.dscr_by_year, 1.5);
      const threshold = 1.3;

      debt.dscr_by_year.forEach((v, i) => {
        const bx = LM + i * barW + 1;
        const bh = (v / maxDscr) * barH;
        const c = v >= 1.3 ? GREEN : v >= 1.0 ? [245, 158, 11] as const : RED;
        pdf.setFillColor(...c);
        pdf.roundedRect(bx, y + barH - bh, barW - 2, bh, 0.6, 0.6, 'F');
        pdf.setFontSize(5);
        pdf.setTextColor(...DARK);
        pdf.setFont('helvetica', 'normal');
        pdf.text(v.toFixed(1), bx + (barW - 2) / 2, y + barH - bh - 1.2, { align: 'center' });
        pdf.setFontSize(5);
        pdf.setTextColor(...DIM);
        pdf.text(`Y${i + 1}`, bx + (barW - 2) / 2, y + barH + 3.5, { align: 'center' });
      });
      // 1.3x reference line
      const refY = y + barH - (threshold / maxDscr) * barH;
      pdf.setDrawColor(...GREEN);
      pdf.setLineWidth(0.3);
      pdf.setLineDashPattern([2, 2], 0);
      pdf.line(LM, refY, RM, refY);
      pdf.setLineDashPattern([], 0);
      pdf.setFontSize(5);
      pdf.setTextColor(...GREEN);
      pdf.setFont('helvetica', 'bold');
      pdf.text('1.3x threshold', RM, refY - 1, { align: 'right' });
      y += barH + 8;
    }
  }

  // ── O&M Breakdown ──
  const om = data.financials?.om_breakdown;
  if (om) {
    sectionTitle('O&M Cost Breakdown');
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`GH\u20B3${data.financials?.om_per_kw ?? 'N/A'}/kWp/year \u2014 per IRENA West Africa benchmarks`, LM, y);
    y += 6;
    const omItems: [string, number | undefined][] = [
      ['Cleaning', om.cleaning],
      ['Inverter Reserve', om.inverter_reserve],
      ['Monitoring', om.monitoring],
      ['Insurance', om.insurance],
      ['Spare Parts', om.spare_parts],
    ];
    const omW = (CW - 20) / 5;
    omItems.forEach(([k, v], i) => {
      const cx = LM + i * (omW + 4);
      pdf.setFillColor(...LIGHT_BG);
      pdf.roundedRect(cx, y, omW, 14, 2, 2, 'F');
      subLabel(k, v != null ? `GH\u20B3${v}/kWp` : 'N/A', cx + 2, omW - 4);
    });
    y += 20;
  }

  // ── Sensitivity Tornado ──
  if (data.lossParams && data.npv != null && data.capex != null) {
    sectionTitle('Sensitivity Analysis \u2014 NPV Tornado');
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'normal');
    pdf.text('\u00B120% variation in each parameter (all else held constant)', LM, y);
    y += 5;

    const baseNpv = data.npv;
    const capex = data.capex;
    const annualSavings = (data.annualEnergy ?? 0) * (data.lossParams.effective_tariff ?? 1.90);
    const degradationPct = (data.lossParams.degradation_rate_pct ?? 0.5) / 100;
    const tariffEscPct = (data.lossParams.tariff_escalation_pct ?? 3.0) / 100;
    const factor = 0.20;
    const wacc = 0.08;
    const lifetime = 25;

    function calcNpv(dRate: number, tEsc: number, c: number, s: number) {
      let n = -c;
      for (let yr = 1; yr <= lifetime; yr++) {
        const deg = yr === 1 ? 0.98 : 0.98 * Math.pow(1 - dRate, yr - 1);
        const esc = Math.pow(1 + tEsc, yr - 1);
        const netCash = s * deg * esc - 320 * (data.capacityKw ?? 1) * Math.pow(1.02, yr - 1);
        n += netCash / Math.pow(1 + wacc, yr);
      }
      return n;
    }

    const tornadoRows: { name: string; low: number; high: number }[] = [
      { name: 'Tariff Escalation', low: calcNpv(degradationPct, tariffEscPct * (1 - factor), capex, annualSavings), high: calcNpv(degradationPct, tariffEscPct * (1 + factor), capex, annualSavings) },
      { name: 'Degradation Rate', low: calcNpv(degradationPct * (1 + factor), tariffEscPct, capex, annualSavings), high: calcNpv(degradationPct * (1 - factor), tariffEscPct, capex, annualSavings) },
      { name: 'CAPEX', low: calcNpv(degradationPct, tariffEscPct, capex * (1 - factor), annualSavings), high: calcNpv(degradationPct, tariffEscPct, capex * (1 + factor), annualSavings) },
      { name: 'Irradiance (Yield)', low: calcNpv(degradationPct, tariffEscPct, capex, annualSavings * (1 - factor)), high: calcNpv(degradationPct, tariffEscPct, capex, annualSavings * (1 + factor)) },
    ];

    const deltas = tornadoRows.map(r => ({
      ...r,
      lowDelta: r.low - baseNpv,
      highDelta: r.high - baseNpv,
      range: Math.abs(r.high - r.low),
    })).sort((a, b) => b.range - a.range);

    const maxDelta = Math.max(...deltas.map(d => Math.max(Math.abs(d.lowDelta), Math.abs(d.highDelta))), 1);
    const barAreaW = CW - 70;
    const halfBar = barAreaW / 2;
    const barH = 5;

    deltas.forEach(d => {
      checkPage(8);
      // label
      pdf.setFontSize(7);
      pdf.setTextColor(...DARK);
      pdf.setFont('helvetica', 'normal');
      pdf.text(d.name, LM, y + barH);
      // low bar (left of center)
      const lowW = (Math.abs(d.lowDelta) / maxDelta) * halfBar;
      if (lowW > 0) {
        pdf.setFillColor(...RED);
        pdf.roundedRect(LM + 40 + halfBar - lowW, y, lowW, barH, 0.5, 0.5, 'F');
      }
      // high bar (right of center)
      const highW = (Math.abs(d.highDelta) / maxDelta) * halfBar;
      if (highW > 0) {
        pdf.setFillColor(...GREEN);
        pdf.roundedRect(LM + 40 + halfBar, y, highW, barH, 0.5, 0.5, 'F');
      }
      // delta values
      pdf.setFontSize(5);
      pdf.setTextColor(239, 68, 68);
      pdf.text(`-${formatGHS(Math.abs(d.lowDelta))}`, LM + 40 + halfBar - lowW - 1, y + barH, { align: 'right' });
      pdf.setTextColor(...GREEN);
      pdf.text(`+${formatGHS(Math.abs(d.highDelta))}`, LM + 40 + halfBar + highW + 1, y + barH);
      y += 9;
    });
    y += 3;
    pdf.setFontSize(6);
    pdf.setTextColor(...DIM);
    pdf.text(`Base NPV: ${formatGHS(baseNpv)}`, LM, y);
    y += 4;
  }

  // ── PAGE 3: Environmental ──
  pdf.addPage();
  y = 20;

  sectionTitle('Environmental Impact');
  const env = data.environmentalMetrics;
  if (env) {
    textRow('PM2.5 (Ambient)', env.pm_data_available && env.mean_pm25 != null ? `${env.mean_pm25.toFixed(2)} \u00B5g/m\u00B3` : 'Not yet available');
    textRow('PM10 (Ambient)', env.pm_data_available && env.mean_pm10 != null ? `${env.mean_pm10.toFixed(2)} \u00B5g/m\u00B3` : 'Not yet available');
    textRow('Cleaning Events / Month', env.mean_cleaning_events_monthly?.toFixed(1) ?? '0');
    y += 2;
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.setFont('helvetica', 'italic');
    pdf.text('PM data requires ground-level sensors; satellite sources (NASA POWER) do not provide particulate measurements.', LM, y);
    y += 4;
    pdf.text('Cleaning events estimated from rainfall events (>0.5 mm); heavy rain self-cleans panels.', LM, y);
    y += 6;
  } else {
    pdf.setFontSize(8);
    pdf.setTextColor(...DIM);
    pdf.text('Environmental metrics not available for this simulation.', LM, y);
    y += 8;
  }

  // Carbon
  sectionTitle('Carbon Equivalence');
  if (data.annualEnergy) {
    const co2 = (data.annualEnergy * 0.0005).toFixed(1);
    pdf.setFontSize(9);
    pdf.setTextColor(...DARK);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`Based on ${formatEnergy(data.annualEnergy)} annual yield, this system avoids an estimated ${co2} tonnes CO\u2082 per year`, LM, y, { maxWidth: CW });
    y += 5;
    pdf.setFontSize(7);
    pdf.setTextColor(...DIM);
    pdf.text('(Using Ghana grid emission factor of ~0.5 kg CO\u2082/kWh)', LM, y);
    y += 6;
  }

  // Uncertainty disclosure
  sectionTitle('Uncertainty Disclosure');
  pdf.setFontSize(7);
  pdf.setTextColor(...DARK);
  pdf.setFont('helvetica', 'normal');
  const discText = 'Resource uncertainty is calibrated, not assumed: regime-conditional conformal intervals validated leave-one-station-out on Tier-1 pyranometers (P90 empirical coverage \u2248 90%). The Monte Carlo P50/P90/P99 spread combines this calibrated resource+model term with Harmattan soiling (\u00B112%), hardware tolerance (\u00B13%), tariff regulation risk (\u00B115%), degradation variance (\u00B10.2%/yr), and grid availability (\u00B15%). P90 = yield exceeded in 90% of years (bankable, per IEC 61724); P99 = worst-case downside.';
  pdf.text(discText, LM, y, { maxWidth: CW });
  y += 18;

  // Footer
  const pages = pdf.getNumberOfPages();
  for (let p = 1; p <= pages; p++) {
    pdf.setPage(p);
    pdf.setFontSize(6);
    pdf.setTextColor(160, 160, 160);
    pdf.setFont('helvetica', 'normal');
    pdf.text('UNISOLAR Enterprise Edition | Confidential', LM, H - 8);
    pdf.text(`Page ${p} of ${pages}`, RM, H - 8, { align: 'right' });
    // gold line
    pdf.setFillColor(...GOLD);
    pdf.rect(0, H - 12, W, 0.4, 'F');
  }

  const blob = pdf.output('blob');
  const dateStr = new Date().toISOString().slice(0, 10);
  downloadBlob(blob, `${filename}_${dateStr}.pdf`);
}

// ---------- Compatibility ----------

/**
 * Export a DOM element as PNG or PDF.
 * For map views — uses html2canvas.
 */
export async function exportAndDownload(
  container: HTMLElement,
  options: { format?: 'png' | 'pdf'; filename?: string; scale?: number } = { format: 'png' }
): Promise<void> {
  const name = options.filename ?? 'unisolar-export';
  await exportMapPNG(container, name);
}

// ---------- PNG Map Export ----------

export async function exportMapPNG(container: HTMLElement, filename = 'unisolar-map'): Promise<void> {
  const html2canvas = (await import('html2canvas')).default;
  const canvas = await html2canvas(container, {
    scale: 2,
    useCORS: true,
    allowTaint: true,
    backgroundColor: null,
    logging: false,
  });
  canvas.toBlob((blob) => {
    if (blob) downloadBlob(blob, `${filename}.png`);
  }, 'image/png', 1.0);
}
