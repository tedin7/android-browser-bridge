#!/usr/bin/env python3
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tempfile
import shutil
import zipapp

root = Path(__file__).resolve().parent
with ZipFile(root / "android-browser-bridge.xpi", "w", ZIP_DEFLATED) as archive:
    for file in sorted((root / "extension").iterdir()):
        if file.is_file() and file.name != ".amo-upload-uuid":
            archive.write(file, file.name)
print(root / "android-browser-bridge.xpi")
with tempfile.TemporaryDirectory() as directory:
    staging = Path(directory)
    for name in ("operations.json", "operation_registry.py", "client_registration.py", "native_artifacts.py", "client_auth.py", "task_store.py", "task_runtime.py", "action_store.py", "step_runtime.py", "protocol_adapter.py", "mcp_app.py", "mcp_tasks.py", "tool_schema_policy.py", "observation_cache.py", "bridge.py", "mcp_server.py", "mcp_guidance.py", "browser_navigation.py", "command_order.py", "response_policy.py", "launcher.py", "connection.py", "install.html", "test_page.html", "test_frame.html", "android-browser-bridge.xpi"):
        shutil.copy2(root / name, staging / name)
    shutil.copytree(root / "apps", staging / "apps")
    (staging / "__main__.py").write_text('''import sys, tempfile, zipfile, runpy
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="browser-bridge-") as directory:
    with zipfile.ZipFile(sys.argv[0]) as archive:
        archive.extractall(directory)
    sys.path.insert(0, directory)
    runpy.run_path(str(Path(directory) / "launcher.py"), run_name="__main__")
''')
    zipapp.create_archive(staging, root / "android-browser-mcp.pyz", interpreter="/usr/bin/env python3", compressed=True)
print(root / "android-browser-mcp.pyz")
with ZipFile(root / "android-browser-bridge-bundle.zip", "w", ZIP_DEFLATED) as archive:
    names = ["AGENTS.md", "README.md", "LICENSE", "PRIVACY.md", "RELEASE_NOTES.md", "operations.json", "operation_registry.py", "client_registration.py", "native_artifacts.py", "client_auth.py", "task_store.py", "task_runtime.py", "action_store.py", "step_runtime.py", "protocol_adapter.py", "mcp_app.py", "mcp_tasks.py", "tool_schema_policy.py", "observation_cache.py", "bridge.py", "mcp_server.py", "mcp_guidance.py", "browser_navigation.py", "command_order.py", "response_policy.py", "launcher.py", "connection.py", "install.py", "agent_integration.py", "build.py", "test_bridge.py", "test_navigation.py", "test_attach.py", "test_setup.py", "test_extension.js", "test_firefox.py", "profile_android.py", "profile_client.py", "test_page.html", "test_frame.html", "smoke_mcp.py", "install.html", "android-browser-bridge.xpi", "android-browser-mcp.pyz"]
    if (root / "interaction_suite.py").exists(): names.append("interaction_suite.py")
    for optional in ("test_multiserver.js", "test_multiserver_firefox.py", "test_options.js", "test_response_policy.py", "benchmark_response.py", "desktop_audit.py", "test_layout.js", "test_viewport.js", "test_claude_install.py", "browser_cli.py", "profile_client.py", "validate_runtime.py", "test_fixture_serving.py", "operation_validator.js", "test_generated_contracts.js", "test_output_contracts.py", "benchmark_fixture.py", "benchmark_hooks.py", "benchmark_setup.py", "benchmark_agent.py", "test_benchmark_fixture.py", "test_install_rollback.py", "generate_operations.py", "test_operation_registry.py", "test_browser_cli.py", "test_broker_retention.py", "test_action_store.py", "test_mcp_recovery.py", "test_step_runtime.py", "test_leases.js", "test_dom_projection.js", "test_game_input.js", "test_observation_cache.py", "test_client_auth.py", "release_gate.py", "test_release_gate.py", "test_broker_security.py", "test_protocol_adapter.py", "test_task_store.py", "test_task_runtime.py", "test_native_artifacts.py", "test_client_registration.py", "test_webmcp_adapter.js", "test_webmcp_options.js", "desktop_cdp.mjs", "test_desktop_cdp.mjs", "test_mcp_app.py", "test_mcp_tasks.py", "test_tool_schema_policy.py", "test_mcp_app.js", "test_webmcp_integration.js", "test_mcp_app_panel.mjs"):
        if (root / optional).exists(): names.append(optional)
    for name in dict.fromkeys(names):
        archive.write(root / name, name)
    for directory in ("extension", "docs", "agent-skills", "apps"):
        for file in sorted((root / directory).rglob("*")):
            if file.is_file() and file.name != ".amo-upload-uuid":
                archive.write(file, file.relative_to(root))
    for file in sorted((root / "companion").rglob("*")):
        if file.is_file() and not any(part in {'build','.gradle'} for part in file.relative_to(root/'companion').parts) and file.name != 'local.properties' and file.suffix not in {'.apk','.jks','.keystore'}:
            archive.write(file,file.relative_to(root))
print(root / "android-browser-bridge-bundle.zip")
