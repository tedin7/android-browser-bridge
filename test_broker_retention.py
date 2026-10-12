import unittest
from bridge import Broker, BrokerError

class RetentionTests(unittest.TestCase):
    def ready(self, **options):
        b=Broker(**options);b.handle('/api/poll',{'device':'tablet'});return b
    def command(self,b,client='admin'):
        return b.handle('/api/command',{'device':'tablet','op':'read','_client':client})['id']
    def finish(self,b,identifier,result=None):
        b.handle('/api/poll',{'device':'tablet'})
        b.handle('/api/result',{'device':'tablet','id':identifier,'result':result or {'ok':True}})
    def test_history_does_not_consume_active_capacity(self):
        b=self.ready(active_limit=2,client_limit=2,history_limit=3)
        for _ in range(12):self.finish(b,self.command(b))
        self.assertLessEqual(len(b.commands),3)
        self.command(b);self.command(b)
        with self.assertRaises(BrokerError) as error:self.command(b)
        self.assertEqual(error.exception.code,'QUEUE_FULL')
    def test_client_quotas_and_other_client_progress(self):
        b=self.ready(active_limit=3,client_limit=1)
        self.command(b,'one')
        with self.assertRaises(BrokerError):self.command(b,'one')
        self.command(b,'two')
    def test_late_result_terminal_and_next_result_accepted(self):
        b=self.ready(history_limit=1)
        first=self.command(b);self.finish(b,first)
        second=self.command(b);self.finish(b,second)
        with self.assertRaises(BrokerError) as error:b.handle('/api/result',{'device':'tablet','id':first,'result':{}})
        self.assertEqual(error.exception.code,'COMMAND_EXPIRED')
        third=self.command(b);self.finish(b,third)
        self.assertEqual(b.handle('/api/status',{'id':third})['state'],'done')
    def test_history_bytes_and_private_recovery_hints(self):
        b=self.ready(history_bytes=1000)
        identifier=b.handle('/api/command',{'device':'tablet','op':'fill','args':{'value':'private','selector':'private-selector'}})['id']
        status=b.handle('/api/status',{'id':identifier})
        self.assertEqual(status['operation'],'fill')
        self.assertNotIn('private',str(status))
        self.finish(b,identifier,{'text':'x'*2000})
        self.assertNotIn(identifier,b.commands)

if __name__=='__main__':unittest.main()
