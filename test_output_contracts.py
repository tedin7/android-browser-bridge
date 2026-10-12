import json
import subprocess
import unittest
from pathlib import Path
from operation_registry import REGISTRY, validate_arguments, validate_result


class GeneratedContractTests(unittest.TestCase):
    def test_every_operation_declares_raw_output(self):
        for name, spec in REGISTRY['operations'].items():
            self.assertIn(spec['outputSchema']['type'], ('object', 'array'), name)
            with self.assertRaises(ValueError):
                validate_result(name, 'invalid scalar result')

    def test_batch_inheritance_does_not_mutate(self):
        args = {'tabId': 7, 'workflowId': 'flow', 'leaseGeneration': 'generation',
                'steps': [{'op': 'release_lease'}]}
        before = json.dumps(args)
        validate_arguments('batch', args)
        self.assertEqual(json.dumps(args), before)
        with self.assertRaises(ValueError):
            validate_arguments('batch', {'steps': args['steps']})

    def test_output_batch_recurses_and_nullable_fields(self):
        validate_result('wait', {'state': 'detached', 'count': 0, 'element': None})
        validate_result('batch', {'completed': 1, 'results': [{'op': 'open', 'result': {'id': 7}}]})
        with self.assertRaises(ValueError):
            validate_result('batch', {'completed': 1, 'results': [{'op': 'open', 'result': {'id': False}}]})
        with self.assertRaises(ValueError):
            validate_result('screenshot', {'mimeType': 'text/plain', 'data': 'x', 'tabId': 7})

    def test_generated_js_contracts(self):
        subprocess.run(['node', 'test_generated_contracts.js'], check=True, cwd=Path(__file__).parent,
                       capture_output=True, text=True)

if __name__ == '__main__':
    unittest.main()
