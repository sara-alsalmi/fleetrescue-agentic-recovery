from .scenarios import make_scenario

engine = make_scenario("normal")
engine.tick(40)
print(engine.snapshot())
