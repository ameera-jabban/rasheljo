import factory

from catalog.models import Brand, Category, Product, ProductAttribute


class BrandFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Brand
    name_en = factory.Sequence(lambda n: f"Brand {n}")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
    name_en = factory.Sequence(lambda n: f"Category {n}")


class ProductAttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductAttribute
    attribute_type = "skin_type"
    value_en = factory.Sequence(lambda n: f"Skin Type {n}")


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product
    sku = factory.Sequence(lambda n: f"SKU-{n:04d}")
    name_en = factory.Sequence(lambda n: f"Product {n}")
    brand = factory.SubFactory(BrandFactory)
    category = factory.SubFactory(CategoryFactory)
    price = "10.00"
    stock = 50
