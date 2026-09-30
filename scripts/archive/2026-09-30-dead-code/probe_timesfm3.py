#!/usr/bin/env python3
"""TimesFM-3.0 CPU Offline Probe - 7 checks (Final)"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import sys
import traceback

results = []

def check(name, fn):
    try:
        result = fn()
        results.append((name, "PASS", result))
        print(f"✅ {name}: {result}")
        return True
    except Exception as e:
        results.append((name, "FAIL", str(e)))
        print(f"❌ {name}: {e}")
        traceback.print_exc()
        return False

# Check 1: Import timesfm3
def check_import():
    import timesfm3
    ver = timesfm3.__version__ if hasattr(timesfm3, "__version__") else "unknown"
    return f"timesfm3 version {ver}"

# Check 2: TimesFM3Forecaster class exists
def check_forecaster_class():
    from timesfm3 import TimesFM3Forecaster
    return "TimesFM3Forecaster imported"

# Check 3: Load 3.0 weights
def check_load_weights():
    from timesfm3 import TimesFM3Forecaster
    model = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch")
    return f"Model loaded, type: {type(model).__name__}"

# Check 4: Covariate entry signature
def check_covariate_signature():
    from timesfm3 import TimesFM3Forecaster
    import inspect
    sig = inspect.signature(TimesFM3Forecaster.predict)
    params = list(sig.parameters.keys())
    has_covariates = any("covariate" in p.lower() for p in params)
    return f"predict params: {params}, has_covariates: {has_covariates}"

# Check 5: Basic prediction
def check_basic_prediction():
    from timesfm3 import TimesFM3Forecaster
    import numpy as np
    model = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch")
    context = np.random.randn(10).tolist()
    result = model.predict(context=context, horizon=5)
    result_type = type(result).__name__
    return f"result type: {result_type}"

# Check 6: ForecastOutput structure
def check_forecast_output():
    from timesfm3 import TimesFM3Forecaster
    import numpy as np
    model = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch")
    context = np.random.randn(10).tolist()
    result = model.predict(context=context, horizon=5)
    # Check ForecastOutput attributes
    attrs = [a for a in dir(result) if not a.startswith("_")]
    has_point = "point" in attrs or "mean" in attrs
    has_quantile = "quantile" in attrs or "quantiles" in attrs
    return f"ForecastOutput attrs: {attrs}, has_point: {has_point}, has_quantile: {has_quantile}"

# Check 7: Memory RSS after cold load
def check_memory_rss():
    import resource
    from timesfm3 import TimesFM3Forecaster
    model = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch")
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return f"RSS: {rss_mb:.1f} MB"

print("=" * 60)
print("TimesFM-3.0 CPU Probe - 7 Checks (Final)")
print("=" * 60)

check("1. Import timesfm3", check_import)
check("2. TimesFM3Forecaster class", check_forecaster_class)
check("3. Load 3.0 weights", check_load_weights)
check("4. Covariate signature", check_covariate_signature)
check("5. Basic prediction", check_basic_prediction)
check("6. ForecastOutput structure", check_forecast_output)
check("7. Memory RSS", check_memory_rss)

print("\n" + "=" * 60)
passed = sum(11 for _, status, _ in results if status == "PASS")
print(f"Results: {passed}/{len(results)} passed")
if passed == len(results):
    print("✅ ALL CHECKS PASSED - Gate OPEN")
    sys.exit(0)
else:
    print("❌ SOME CHECKS FAILED - Gate CLOSED")
    sys.exit(1)
