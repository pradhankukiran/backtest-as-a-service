from rest_framework.routers import DefaultRouter

from bars.api import BarViewSet, SymbolViewSet

from .api import BacktestRunViewSet, StrategyViewSet

router = DefaultRouter()
router.register("symbols", SymbolViewSet)
router.register("bars", BarViewSet)
router.register("strategies", StrategyViewSet)
router.register("runs", BacktestRunViewSet)

urlpatterns = router.urls
