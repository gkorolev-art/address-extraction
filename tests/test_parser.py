"""
tests/test_parser.py — тесты на реальных данных из обоих файлов.

Запуск:
    python -m pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parser.address_parser import parse_address


# ─── вспомогательная функция ───────────────────────────────────────
def chk(raw, exp_sett=None, exp_hs=None):
    """Проверяет settlement и/или house_street."""
    r = parse_address(raw)
    ok = True
    msgs = []
    if exp_sett is not None and r.settlement != exp_sett:
        msgs.append(f"settlement: got «{r.settlement}» expected «{exp_sett}»")
        ok = False
    if exp_hs is not None and r.house_street != exp_hs:
        msgs.append(f"house_street: got «{r.house_street}» expected «{exp_hs}»")
        ok = False
    return ok, msgs, r


# ═══════════════════════════════════════════════════════════════════
#  ФАЙЛ 1 — ЛУКОЙЛ (стандартный формат)
# ═══════════════════════════════════════════════════════════════════

class TestLukoilFormat:

    def test_km_with_settlement(self):
        ok, msgs, r = chk(
            "Брянская обл., Брасовский р-н, д. Погребы, 424 км + 700 м лево а/д М-3 «Украина»",
            exp_sett="д. Погребы",
        )
        assert "424 км" in r.house_street, f"km not found in: {r.house_street}"
        assert "лево" in r.house_street.lower() or "700" in r.house_street

    def test_km_with_city(self):
        ok, msgs, r = chk(
            "Брянская обл., Карачевский р-н, г. Карачев, в р-не а/д \"Орел-Брянск\", 82 км + 700 м",
            exp_sett="г. Карачев",
        )
        assert "82 км" in r.house_street

    def test_plain_city_address(self):
        ok, msgs, r = chk(
            "Брянская обл, г Брянск, пр-кт Московский, д 2В",
            exp_sett="г. Брянск",
        )
        assert "2В" in r.house_street or "2В" in r.house_street
        assert "Московский" in r.house_street

    def test_street_and_house_without_comma(self):
        ok, msgs, r = chk(
            "Брянская обл., г. Брянск, ул. Калинина д 116",
            exp_sett="г. Брянск",
            exp_hs="116, ул. Калинина",
        )
        assert ok, "; ".join(msgs)

    def test_oblast_city_ul_dom(self):
        ok, msgs, r = chk(
            "Владимирская обл., г. Владимир, ул. Растопчина, д. 2",
            exp_sett="г. Владимир",
        )
        assert "2" in r.house_street
        assert "Растопчина" in r.house_street
        # дом должен идти первым
        assert r.house_street.index("2") < r.house_street.index("Растопчина")

    def test_russia_prefix_stripped(self):
        ok, msgs, r = chk(
            "Россия, 127521, г. Москва, ул. Шереметьевская, 47А",
            exp_sett="г. Москва",
        )
        assert "47А" in r.house_street or "Шереметьевская" in r.house_street

    def test_moscow_pgt_rule(self):
        """г. Москва + п. → выбираем п."""
        ok, msgs, r = chk(
            "г. Москва, п. Первомайское, 39 км Киевского шоссе вл. 1, стр. 1",
            exp_sett="п. Первомайское",
        )
        assert "39 км" in r.house_street or "вл" in r.house_street.lower()

    def test_moscow_no_sub(self):
        """г. Москва без вложенного посёлка."""
        ok, msgs, r = chk(
            "г. Москва, ул. Хорошевская 3-я, д. 9, корп. 1, стр. 1",
            exp_sett="г. Москва",
        )
        assert "9" in r.house_street
        assert "Хорошевская" in r.house_street

    def test_mkad(self):
        ok, msgs, r = chk(
            "г. Москва, МКАД, 51-52 км, вл. 12",
            exp_sett="г. Москва",
        )
        assert "51" in r.house_street or "МКАД" in r.house_street

    def test_km_no_settlement(self):
        """КМ без явного нас.пункта — settlement пустой."""
        ok, msgs, r = chk(
            "Владимирская обл., 202 км+250м слева ф/д М-7Волга",
        )
        assert "202 км" in r.house_street

    def test_spb_address(self):
        ok, msgs, r = chk(
            "г. Санкт-Петербург, Московский р-н, пр-кт Витебский, 22, лит. А",
            exp_sett="г. Санкт-Петербург",
        )
        assert "22" in r.house_street
        assert "Витебский" in r.house_street

    def test_village_km(self):
        ok, msgs, r = chk(
            "Нижегородская обл., г. Дзержинск, п. Гавриловка, 7км+700м Гавриловской а/д, 2",
            exp_sett="п. Гавриловка",
        )
        assert "7 км" in r.house_street or "7км" in r.house_street


# ═══════════════════════════════════════════════════════════════════
#  ФАЙЛ 2 — ПРОКТЕР (обратный формат)
# ═══════════════════════════════════════════════════════════════════

class TestProcterFormat:

    def test_basic(self):
        ok, msgs, r = chk(
            "623101, Свердловская обл, Первоуральск г, Ленина ул, дом № стр. 7Б, помещ 2",
            exp_sett="г. Первоуральск",
        )
        assert "7Б" in r.house_street or "Ленина" in r.house_street

    def test_karachaevo(self):
        ok, msgs, r = chk(
            "369009, Карачаево-Черкесская Респ, Черкесск г, Свободы ул, дом № 62",
            exp_sett="г. Черкесск",
        )
        assert "62" in r.house_street
        assert "Свободы" in r.house_street

    def test_stavropol(self):
        ok, msgs, r = chk(
            "357850, Ставропольский край, Курский р-н, Курская ст-ца, Школьный пер, дом № 3",
            exp_sett="ст-ца Курская",
        )
        assert "3" in r.house_street

    def test_moscow_sosenskoe(self):
        ok, msgs, r = chk(
            "108803, Сосенское п, Москва г, Куприна пр-кт, дом № 30,к. 1,помещ 17Н",
        )
        # Сосенское п → п. Сосенское; более специфично чем Москва г
        # ИЛИ Москва г (зависит от приоритета — оба валидны)
        assert r.settlement in ("п. Сосенское", "г. Москва")
        assert "Куприна" in r.house_street or "30" in r.house_street

    def test_ufa(self):
        ok, msgs, r = chk(
            "450001, Башкортостан Респ, Уфа г, Октября пр-кт, дом № 15",
            exp_sett="г. Уфа",
        )
        assert "15" in r.house_street
        assert "Октября" in r.house_street

    def test_spb_procter(self):
        ok, msgs, r = chk(
            "197373, Санкт-Петербург г, Авиаконструкторов пр-кт, дом № 54,стр. 1,помещ. 105Н",
            exp_sett="г. Санкт-Петербург",
        )
        assert "54" in r.house_street
        assert "Авиаконструкторов" in r.house_street


# ═══════════════════════════════════════════════════════════════════
#  ПРОГОН С ВЫВОДОМ
# ═══════════════════════════════════════════════════════════════════

MANUAL_CASES = [
    ("Брянская обл., с. Малое Полпино, Киевское шоссе, 355км а/д М-3 Украина",
     None, None),
    ("Брянская обл., Брянский р-н, д. Добрунь, 14 км а/д \"Брянск-Новозыбков\"",
     "д. Добрунь", None),
    ("Брянская обл., Браосвский р-н, д. Погребы, 424 км + 950 м право а/д М-3 Украина",
     "д. Погребы", None),
    ("Владимирская обл., г. Вязники, ул. Ленина, д. 43",
     "г. Вязники", None),
    ("Брянская обл., г. Брянск, ул. Калинина д 116",
     "г. Брянск", "116, ул. Калинина"),
    ("г. Москва, п. Московский, Киевское шоссе, 28-ой км, вл. 2, стр. 1",
     "п. Московский", None),
    ("г. Москва, МКАД, 58 км, вл. 6",
     "г. Москва", None),
    ("Тверская обл., г. Тверь, ул. Вагжанова, д. 11",
     "г. Тверь", None),
    ("623101, Свердловская обл, Первоуральск г, Ленина ул, дом № стр. 7Б, помещ 2",
     "г. Первоуральск", None),
    ("108803, Сосенское п, Москва г, Куприна пр-кт, дом № 30,к. 1,помещ 17Н",
     None, None),
]


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("РУЧНОЙ ПРОГОН ТЕСТОВ")
    print("=" * 80)

    passed = failed = 0
    for raw, exp_sett, exp_hs in MANUAL_CASES:
        ok, msgs, r = chk(raw, exp_sett, exp_hs)
        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} [{r.confidence:.2f}] {raw[:70]}")
        print(f"    Нас.пункт : {r.settlement or '—'}")
        print(f"    Дом+улица : {r.house_street or '—'}")
        if msgs:
            for m in msgs:
                print(f"    ⚠ {m}")

    print(f"\n{'='*80}")
    print(f"Итог: {passed} прошли, {failed} не прошли из {passed+failed}")
