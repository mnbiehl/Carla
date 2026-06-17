from carla_mcp.tools.spectrum import analyze_wav
from .fixtures_spectrum import pink_noise, pink_plus_resonance


ZONE_KEYS = {"sub", "low", "mud", "boxiness", "presence",
             "harshness", "sibilance", "air"}


def test_all_zones_present(spectrum_fixtures_dir):
    wav = pink_noise(spectrum_fixtures_dir / "pink_zones.wav", seconds=1.0)
    r = analyze_wav(str(wav))
    assert set(r["zones"].keys()) == ZONE_KEYS
    for z in r["zones"].values():
        assert "f_lo" in z and "f_hi" in z and "rms_db" in z and "vs_pink_db" in z


def test_mud_resonance_lifts_mud_zone(spectrum_fixtures_dir):
    wav = pink_plus_resonance(spectrum_fixtures_dir / "pink_300_zone.wav",
                              freq_hz=300.0, q=4.0, seconds=2.0)
    r = analyze_wav(str(wav))
    assert r["zones"]["mud"]["vs_pink_db"] > 3
