"""Bounded Actions worker; live jobs start at :00, other sources every 15 minutes."""
import argparse
import asyncio
import json
import logging
import math
import subprocess
import time
from pathlib import Path

from backend import main as m
from backend.public_snapshot import restore_snapshot, save_snapshot

log=logging.getLogger('actions-collector')


async def collect(source):
    try:
        await asyncio.wait_for(m.collect_one(source),timeout=150 if source not in ('dengta','kuyun') else 55)
    except Exception as exc:
        m.set_status(source,'error',message='采集暂未成功，保留此前数据')
        log.warning('%s: %s',source,type(exc).__name__)


async def main(folder,duration):
    m.DB_PATH=Path('backend/actions-data.db');m.DRAMAS=(m.TITLE,)
    snapshot=folder/'snapshot.json'
    if not snapshot.exists():raise RuntimeError('Missing historical snapshot; refusing to overwrite history')
    restore_snapshot(json.loads(snapshot.read_text(encoding='utf-8')))
    finish=time.monotonic()+duration*60
    slow=None;next_slow=0
    try:
        while time.monotonic()<finish:
            # Recalculate from wall time each cycle; request duration never shifts the clock.
            await asyncio.sleep(max(0,math.floor(time.time()/60)*60+60-time.time()))
            if time.monotonic()>=finish:break
            cycle=math.floor(time.time()/60)
            if time.monotonic()>=next_slow and (slow is None or slow.done()):
                slow=asyncio.gather(*(collect(s) for s in m.SOURCES if s not in ('dengta','kuyun')))
                next_slow=time.monotonic()+900
            await asyncio.gather(collect('dengta'),collect('kuyun'))
            # SQLite reads occur on the event-loop thread; browser tasks cannot mutate
            # the database midway through export. Only the Git subprocess runs outside it.
            save_snapshot(folder/'snapshot.json',cycle)
            try:
                await asyncio.to_thread(commit_snapshot,folder,cycle)
                log.info('Published minute snapshot')
            except subprocess.CalledProcessError:
                log.warning('Publish failed; retained local snapshot for the next minute')
    finally:
        if slow and not slow.done():
            slow.cancel()
            await asyncio.gather(slow,return_exceptions=True)
        await m.browsers.close()


def commit_snapshot(folder,cycle):
    for args in [('add','snapshot.json'),('commit','-m','Update public metrics'),('push','--atomic','origin','HEAD:refs/heads/data',f'HEAD:refs/heads/minute-{cycle%12}')]:
        subprocess.run(['git','-C',str(folder),*args],check=True,capture_output=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True);parser.add_argument('--minutes',type=int,default=330)
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    asyncio.run(main(args.data_dir,args.minutes))
