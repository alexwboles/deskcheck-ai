"""Verify a built/extracted portable package without relying on Python at runtime."""
import json
from pathlib import Path
import subprocess
import sys
import uuid


def main():
    app = Path(sys.argv[1]).resolve()
    root = Path(__file__).resolve().parents[1]
    output = root/".qa-output"/("portable-acceptance-"+uuid.uuid4().hex[:12])
    output.mkdir()
    exe = app/"DeskCheck.exe"
    assert exe.is_file() and (app/"DeskCheck Desktop.exe").is_file()
    assert (app/"THIRD-PARTY-LICENSES").is_dir()
    def invoke(args,expected):
        result = subprocess.run([str(exe)]+args,cwd=output,capture_output=True,text=True,timeout=45)
        assert result.returncode == expected,(args,result.returncode,result.stdout,result.stderr)
        return result
    assert "0.2.0" in invoke(["--version"],0).stdout
    invoke(["run",str(app/"examples"/"demo-pass.yaml"),"--config",str(app/"examples"/"config.yaml"),"--driver","mock","--out-dir",str(output/"mock")],0)
    invoke(["run",str(app/"examples"/"denied-app.yaml"),"--config",str(app/"examples"/"config.yaml"),"--driver","mock","--out-dir",str(output/"denied")],1)
    config = {"apps":{"sample-app":{"command":[str(app/"DeskCheckSample.exe"),str(output/"state.json")]}}}
    test = {"version":1,"name":"packaged-native","app":"sample-app","steps":[
        {"type":"launch","app":"sample-app"},{"type":"click","x":80,"y":100},
        {"type":"type","text":"PACKAGED_LITERAL +%^{x} café"},
        {"type":"click","x":100,"y":165},
        {"type":"click","x":80,"y":225},
        {"type":"assert","kind":"control-text","text":"Saved: PACKAGED_LITERAL +%^{x} café"},
        {"type":"screenshot","name":"native"},
        {"type":"assert","kind":"window-visible","window":"sample-app"}]}
    (output/"config.yaml").write_text(json.dumps(config),encoding="utf-8")
    (output/"test.yaml").write_text(json.dumps(test),encoding="utf-8")
    invoke(["run",str(output/"test.yaml"),"--config",str(output/"config.yaml"),"--driver","windows","--out-dir",str(output/"native")],0)
    state = json.loads((output/"state.json").read_text(encoding="utf-8-sig"))
    assert state["text"] == "PACKAGED_LITERAL +%^{x} café" and state["clicks"] == 1,state
    assert (output/"native"/"screenshots"/"native.png").stat().st_size > 100
    assert "PACKAGED_LITERAL" not in (output/"native"/"actions.jsonl").read_text()
    requests = [
        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}},
        {"jsonrpc":"2.0","id":2,"method":"tools/list"},
        {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"run_test","arguments":{"test":"test.yaml"}}},
        {"jsonrpc":"2.0","id":4,"method":"ping"},
    ]
    result = subprocess.run([str(exe),"mcp","--config",str(output/"config.yaml"),"--workspace",str(output),"--driver","windows"],
        input="\n".join(json.dumps(r) for r in requests)+"\n",cwd=output,capture_output=True,text=True,timeout=45)
    assert result.returncode == 0,(result.stdout,result.stderr)
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies) == 4 and not replies[2]["result"]["isError"],replies
    assert json.loads(replies[2]["result"]["content"][0]["text"])["status"] == "pass"
    assert replies[3]["result"] == {}
    print(json.dumps({"status":"pass","mock":"passed","native":"passed","packagedCaptureWorker":"passed","mcpNativeRun":"passed","artifacts":str(output)}))


if __name__ == "__main__":
    main()
