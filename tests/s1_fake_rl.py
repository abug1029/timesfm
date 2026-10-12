def install_fake_rl(monkeypatch, fake):
    import sys
    for mod in list(sys.modules.values()):
        name = getattr(mod, "__name__", "")
        if name == "praxist_supervisor" or name.startswith("sup_"):
            if "rl" in vars(mod):
                monkeypatch.setattr(mod, "rl", fake)
