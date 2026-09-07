#!/usr/bin/env python3
from native_geometry import make_box
from native_orientation import orient_outward, reverse_winding, signed_volume, winding_report


def run() -> None:
    box = make_box((2.0, 3.0, 4.0), name="winding_box")
    report = winding_report(box)
    assert report["status"] == "pass", report
    assert report["classification"] == "outward"
    assert abs(report["signed_volume"] - 24.0) < 1e-9, report

    inside_out = reverse_winding(box, name="inside_out")
    bad = winding_report(inside_out)
    assert bad["status"] == "fail"
    assert bad["classification"] == "inward"
    assert abs(bad["signed_volume"] + 24.0) < 1e-9, bad

    repaired = orient_outward(inside_out, name="repaired")
    repaired_report = winding_report(repaired)
    assert repaired_report["status"] == "pass"
    assert repaired.vertices == box.vertices
    assert signed_volume(repaired) > 0.0
    print("NATIVE ORIENTATION TEST PASS", report["signed_volume"], bad["signed_volume"], repaired_report["signed_volume"])


if __name__ == "__main__":
    run()
