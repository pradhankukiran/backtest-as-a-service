from rest_framework.routers import DefaultRouter

from bars.api import BarViewSet, SymbolViewSet

from .api import BacktestRunViewSet, ParameterSweepViewSet, StrategyViewSet

router = DefaultRouter()
router.register("symbols", SymbolViewSet)
router.register("bars", BarViewSet)
router.register("strategies", StrategyViewSet)
router.register("runs", BacktestRunViewSet)
router.register("sweeps", ParameterSweepViewSet)

urlpatterns = router.urls
