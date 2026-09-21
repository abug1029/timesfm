"""
B6 Shadow Replay: 对比 2.5 vs 3.0 预测质量
"""
import json
import sys
import os
sys.path.insert(0, "/home/abug/timesfm")

from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from data.data_store import DataStore
from scripts.monthly_backtest import run_symbol_backtest, summarize

def main():
    # Load shadow replay input
    with open("/home/abug/timesfm/data/cache/shadow_replay_input.json") as f:
        samples = json.load(f)
    
    print(f"=== B6 Shadow Replay (TimesFM 3.0) ===")
    print(f"样本数: {len(samples)}")
    print()
    
    # Initialize models
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    
    results = []
    for i, sample in enumerate(samples, 1):
        symbol = sample["symbol"]
        variant_id = sample["variant_id"]
        cov_override = sample.get("cov_override")
        covariate_types = sample.get("covariate_types")
        
        print(f"[{i}/{len(samples)}] {symbol} | {variant_id}")
        
        try:
            with DataStore(symbol) as store:
                # Run backtest with 3.0 model
                data = run_symbol_backtest(
                    symbol=symbol,
                    daily_model=daily_model,
                    hourly_model=hourly_model,
                    cov_override=cov_override,
                    cov_combo=covariate_types,
                    max_points=20,  # Limit for speed
                    daily_cache_dir="/home/abug/timesfm/data/cache/daily_pred_v3",
                )
                
                if data is None:
                    print(f"  ❌ No data")
                    continue
                
                # Compute metrics using summarize()
                metrics = summarize(data)
                if metrics is None:
                    print(f"  ❌ Summarize failed")
                    continue
                
                # Extract metrics
                dir_acc = metrics.get("dir_acc", 0)
                endpoint_mape = metrics.get("endpoint_mape", 0)
                n_eff = metrics.get("n_eff", 0)
                
                print(f"  ✅ dir_acc={dir_acc:.3f} | endpoint_mape={endpoint_mape:.2f}% | n_eff={n_eff}")
                
                results.append({
                    "symbol": symbol,
                    "variant_id": variant_id,
                    "dir_acc": dir_acc,
                    "endpoint_mape": endpoint_mape,
                    "n_eff": n_eff,
                })
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    # Save results
    with open("/home/abug/timesfm/data/cache/shadow_replay_30_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print()
    print(f"=== Shadow Replay 完成 ===")
    print(f"成功: {len(results)}/{len(samples)}")
    print(f"结果已保存到 data/cache/shadow_replay_30_results.json")

if __name__ == "__main__":
    main()
