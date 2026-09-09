import inspect
import cascade.features as feat


def test_pca_symbols_are_module_level():
    assert getattr(feat, "PCA", None) is not None
    assert getattr(feat, "StandardScaler", None) is not None
    src = inspect.getsource(feat.calc_pca_momentum)
    assert "from sklearn" not in src