import threading,unittest,urllib.request
from bridge import make_server

class FixtureServingTests(unittest.TestCase):
    def test_broker_serves_fixed_fixture_and_frame_without_separate_daemon(self):
        server=make_server(0,'fixture-only-token')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for path,expected in [('/fixture?large=1',b'Browser Bridge interaction lab'),('/frame',b'frame-button')]:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}'+path,timeout=2) as response:
                    self.assertEqual(response.status,200)
                    self.assertIn(expected,response.read())
                    self.assertEqual(response.headers['Cache-Control'],'no-store')
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/fixture/../../state/token',timeout=2)
        finally:server.shutdown();server.server_close();thread.join();server.broker.action_store.close()
