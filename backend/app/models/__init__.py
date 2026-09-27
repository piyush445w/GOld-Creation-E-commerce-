"""Model package aggregator for Gold Creation.

Re-exports every SQLAlchemy model class from its own module so the rest of the
app can simply ``from app.models import User, Product, Order`` and, crucially,
so that importing ``app.models`` registers every table on the shared
``db.metadata`` before ``db.create_all()`` or Alembic runs.
"""

# Identity, catalogue, and checkout models, imported in dependency order.
from app.models.user import User  # noqa: F401
from app.models.address import Address  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.product_variant import ProductVariant  # noqa: F401
from app.models.product_media import ProductMedia  # noqa: F401
from app.models.category_media import CategoryMedia  # noqa: F401
from app.models.cart import CartItem  # noqa: F401
from app.models.wishlist import WishlistItem  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.coupon import Coupon  # noqa: F401
from app.models.page import Page  # noqa: F401
from app.models.page_media import PageMedia  # noqa: F401
from app.models.site_setting import SiteSetting  # noqa: F401
from app.models.site_asset import SiteAsset  # noqa: F401
# Presentation/content models (banners, menus, CMS pages, site settings, currency).
from app.models.banner import Banner  # noqa: F401
from app.models.navigation_menu import NavigationMenu  # noqa: F401
from app.models.currency import Currency  # noqa: F401
from app.models.review import Review  # noqa: F401
