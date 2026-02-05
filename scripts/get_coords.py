import sys
import os
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, Location

def get_coords():
    session = get_session(init_db())
    locs = session.query(Location).filter(Location.id.in_([1, 2])).all()
    for l in locs:
        print(f"{l.id},{l.name},{l.latitude},{l.longitude}")
    session.close()

if __name__ == "__main__":
    get_coords()
