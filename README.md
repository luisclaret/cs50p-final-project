# ABB SPAJ 141C — Inverse Overcurrent Trip Evaluation

#### Video Demo:  https://youtu.be/Qv7jcR3XHIs

#### Description:

This project evaluates whether an ABB SPAJ 141C inverse-time overcurrent relay would have tripped for a real load-current profile, and if so, when. It reads three-phase current samples recorded every 200 ms by a PQ-Box 150 power-quality recorder installed on a "Car Dumpers" load, models the relay's IEC inverse-time characteristic, accumulates the time integral while the current stays above pickup, and reports the trip instant together with two plots: a downsampled full-day overview and a zoomed window around the trip.

The relay is configured exactly as in the field: a nominal secondary current of 5 A, a current transformer ratio of 120, a pickup of 0.5 times the nominal secondary current (which translates to a 300 A primary pickup), a very inverse (VI) curve, and a time dial (time multiplier) `k`. The program computes, for each phase and each sample, the current multiple

```
M = primary_current / (pickup * i_nominal * ctr)
```

and then applies the relay's inverse-time formula to obtain a trip time `t(M)` for that instantaneous current. The supported IEC/SPAJ curves are normal inverse, very inverse, extremely inverse, and long-time inverse. When the current is at or below pickup the trip time is infinite.

Because the load current is constantly varying rather than constant, the relay does not trip instantaneously at the first overcurrent. Instead the program integrates `dt / t(M)` for each sample while `M > 1` and resets the accumulated value to zero whenever the current falls back below pickup. A trip is declared the moment the accumulator for any phase reaches 1.0, which reproduces the thermal/time characteristic of an inverse-time relay under varying current.

With the default settings the relay does **not** trip for the recorded operating data; a trip only occurs if the time dial is lowered to about `k = 0.227`. This is the main finding of the project: the existing setting leaves a safety margin, and the program lets a protection engineer quantify exactly how much margin there is before the relay would operate.

The repository contains the following files:

- `project.py` — the entire program. It defines the `CurrentData` dataclass (sampled time and the three phase currents), the `RelaySpaj` class (which models the relay with the `multiple`, `trip_time`, and `evaluate_trip` methods, plus a `primary_pickup` property), and the module-level functions `read_current_csv`, `downsample`, `plot_current`, `plot_trip_window`, `parser_commands`, and `main`.
- `test_project.py` — pytest tests for the core logic: CSV parsing, downsampling, the current multiple and trip-time formulas (including the at/below-pickup and invalid-curve cases), the trip evaluation (trip and no-trip scenarios), and the two plotting functions.
- `corrientes.csv` — the full recorded data set (~400,000 samples, tab-separated despite the `.csv` extension).
- `corrientes_ejemplo.csv` — a tiny five-sample excerpt with the same format, used by the tests and for quick experiments.
- `requirements.txt` — the pip-installable dependencies (`matplotlib` and `numpy`).

A few design choices are worth explaining. First, the recorded currents are treated as primary amperes and the pickup is entered as a multiple of the nominal secondary current, which matches how a relay engineer thinks about settings. Second, only the inverse-time overcurrent function is analysed; the relay's high-set instantaneous and earth-fault functions are intentionally out of scope. Third, the time interval between samples is computed from the actual timestamps in the file rather than assuming a fixed 200 ms, so occasional timestamp jitter in the recorder is handled correctly. Fourth, the full-day plot is downsampled (every `step`-th sample) so that hundreds of thousands of points render quickly, while the trip-window plot uses the full-resolution data so no detail is lost around the fault.

The program is run from the command line, with the CSV path required and all relay settings optional:

```
python project.py -p corrientes.csv -pu 0.5 -td 0.285 -c VI -ctr 120 -inom 5 -s 2
```
