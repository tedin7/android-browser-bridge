import unittest
from mcp_app import RESOURCE_URI, MIME_TYPE, read_resource, resource_descriptor, tool_metadata


class AppResourceTests(unittest.TestCase):
    def test_static_local_resource_and_metadata(self):
        self.assertEqual(resource_descriptor()['uri'], RESOURCE_URI)
        self.assertEqual(tool_metadata()['ui']['resourceUri'], RESOURCE_URI)
        resource = read_resource(RESOURCE_URI)['contents'][0]
        self.assertEqual(resource['mimeType'], MIME_TYPE)
        self.assertEqual(resource['_meta']['ui']['csp']['connectDomains'], [])
        self.assertEqual(resource['_meta']['ui']['permissions'], {})
        self.assertIn('ui/initialize', resource['text'])
        self.assertNotIn('<script src=', resource['text'])
        self.assertNotIn('fetch(', resource['text'])
        self.assertNotIn('innerHTML', resource['text'])

    def test_resource_uri_cannot_read_other_files(self):
        for uri in ('../../secret', 'file:///etc/passwd', RESOURCE_URI+'/other'):
            with self.assertRaises(ValueError):
                read_resource(uri)


if __name__ == '__main__':
    unittest.main()
