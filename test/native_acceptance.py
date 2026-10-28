"""Opt-in product acceptance: only our own compiled fixture, no existing apps."""
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deskcheck.drivers.windows import WindowsDriver
from deskcheck.errors import PermissionDenied
from deskcheck.pngutil import decode_png


def main():
    root = Path(__file__).resolve().parents[1]
    exe = root/".qa-output"/"DeskCheckFixture.exe"
    if not exe.is_file():
        raise SystemExit("Compile test/Fixture.cs first")
    run = root/".qa-output"/("native-"+uuid.uuid4().hex[:12])
    run.mkdir()
    driver = WindowsDriver()
    decoy = WindowsDriver()
    try:
        driver.launch("fixture",[str(exe),str(run/"state.json")])
        driver.check_input_target("fixture")
        assert driver.foreground_window() == "fixture"
        driver.click(80,100)
        synthetic = "Literal +%^{braces} 'quoted' café"
        driver.type_text(synthetic)
        driver.click(100,165)
        state = json.loads((run/"state.json").read_text(encoding="utf-8-sig"))
        assert state["text"] == synthetic,state
        assert state["clicks"] == 1,state
        assert state["result"] == "Saved: "+synthetic,state
        driver.screenshot(str(run/"app.png"))
        width,height,_ = decode_png((run/"app.png").read_bytes())
        assert (width,height) == driver.resolution()
        assert width == 640 and height == 340,(width,height)
        for point in ((-1,0),(640,0),(0,340),(99999,99999)):
            try:
                driver.click(*point)
            except PermissionDenied:
                pass
            else:
                raise AssertionError("Out-of-bounds click accepted")
        assert json.loads((run/"state.json").read_text(encoding="utf-8-sig"))["clicks"] == 1
        try:
            driver.check_input_target("another-app")
        except PermissionDenied:
            pass
        else:
            raise AssertionError("Wrong app accepted")
        driver.click(80,100)
        driver.press_key("Tab")
        driver.press_key("Enter")
        state = json.loads((run/"state.json").read_text(encoding="utf-8-sig"))
        assert state["clicks"] == 2,state
        # An unrelated synthetic window covers the target and has OS focus.
        # Input and capture must still target only the pinned first process.
        decoy.launch("decoy",[str(exe),str(run/"decoy.json"),"decoy"])
        driver.click(80,100)
        driver.press_key("End")
        driver.type_text(" + still-bound")
        state = json.loads((run/"state.json").read_text(encoding="utf-8-sig"))
        assert state["text"] == synthetic+" + still-bound",state
        assert json.loads((run/"decoy.json").read_text(encoding="utf-8-sig"))["text"] == ""
        driver.screenshot(str(run/"occluded-app.png"))
        _,_,rows = decode_png((run/"occluded-app.png").read_bytes())
        assert rows[330][630][:3] == (246,249,252),rows[330][630]
        # Wrong-process child selection is rejected before text delivery.
        driver._input_hwnd = decoy._hwnd
        try:
            driver.type_text("MUST_NOT_BE_TYPED")
        except PermissionDenied:
            pass
        else:
            raise AssertionError("Foreign process accepted")
        assert json.loads((run/"decoy.json").read_text(encoding="utf-8-sig"))["text"] == ""
        print(json.dumps({"status":"pass","client_size":[width,height],"state":state,"artifacts":str(run)}))
    finally:
        decoy.close()
        driver.close()


if __name__ == "__main__":
    main()
