"""Optional static MCP Apps resource; adds no browser or credential authority."""
from pathlib import Path

RESOURCE_URI = 'ui://android-browser-bridge/task-panel'
MIME_TYPE = 'text/html;profile=mcp-app'


def resource_descriptor():
    return {'uri': RESOURCE_URI, 'name': 'Browser Bridge task', 'mimeType': MIME_TYPE,
            'description': 'Inspect one existing task and request cooperative cancellation.'}


def tool_metadata():
    return {'ui': {'resourceUri': RESOURCE_URI, 'visibility': ['model', 'app']}}


def read_resource(uri):
    if uri != RESOURCE_URI:
        raise ValueError('Unknown app resource')
    html = Path(__file__).with_name('apps').joinpath('task-panel.html').read_text()
    return {'contents': [{'uri': RESOURCE_URI, 'mimeType': MIME_TYPE, 'text': html,
                         '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': [], 'frameDomains': []},
                                          'permissions': {}}}}]}
