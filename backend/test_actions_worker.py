from pathlib import Path
import subprocess
import tempfile
import unittest
from backend.actions_worker import commit_snapshot


class PublishTests(unittest.TestCase):
    def test_detached_runner_can_atomically_create_minute_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);remote=root/'remote.git';repo=root/'runner'
            def git(*args):return subprocess.check_output(['git',*map(str,args)],stderr=subprocess.STDOUT,text=True).strip()
            git('init','--bare',remote);git('clone',remote,repo)
            git('-C',repo,'config','user.name','Test');git('-C',repo,'config','user.email','test@example.invalid')
            (repo/'snapshot.json').write_text('{"version":1}')
            git('-C',repo,'add','.');git('-C',repo,'commit','-m','Initial')
            git('-C',repo,'push','origin','HEAD:refs/heads/data')
            git('-C',repo,'checkout','--detach')
            (repo/'snapshot.json').write_text('{"version":2}')
            commit_snapshot(repo,123)
            expected=git('-C',repo,'rev-parse','HEAD')
            self.assertEqual(git('--git-dir',remote,'rev-parse','refs/heads/data'),expected)
            self.assertEqual(git('--git-dir',remote,'rev-parse','refs/heads/minute-3'),expected)


if __name__=='__main__':unittest.main()
