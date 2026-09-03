def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: 真模型/真数据集成测试 (分钟级), 常规回归用 -m 'not slow' 排除")
