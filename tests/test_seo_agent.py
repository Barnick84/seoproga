import pytest
from pydantic import ValidationError

from services.seo_agent import Structure, StructureItem


class TestStructurePydantic:
    def test_valid_structure(self):
        data = {"structure": [{"tag": "h2", "text": "Заголовок"}]}
        model = Structure.model_validate(data)
        assert len(model.structure) == 1
        assert model.structure[0].tag == "h2"

    def test_invalid_tag(self):
        data = {"structure": [{"tag": "h4", "text": "Заголовок"}]}
        with pytest.raises(ValidationError):
            Structure.model_validate(data)

    def test_invalid_item_missing_text(self):
        data = {"structure": [{"tag": "h2"}]}
        with pytest.raises(ValidationError):
            Structure.model_validate(data)

    def test_valid_structure_multiple_items(self):
        data = {
            "structure": [
                {"tag": "h2", "text": "Основной раздел"},
                {"tag": "h3", "text": "Подраздел"},
            ]
        }
        model = Structure.model_validate(data)
        assert model.structure[0].tag == "h2"
        assert model.structure[1].tag == "h3"


class TestStructureItemPydantic:
    def test_valid_h2(self):
        item = StructureItem(tag="h2", text="Тестовый заголовок")
        assert item.tag == "h2"

    def test_valid_h3(self):
        item = StructureItem(tag="h3", text="Подзаголовок")
        assert item.tag == "h3"

    def test_text_too_short(self):
        with pytest.raises(ValidationError):
            StructureItem(tag="h2", text="A")

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            StructureItem(tag="h2", text="X" * 301)
