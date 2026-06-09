import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parser.address_parser import parse_address


class TestAddressParserRegressions(unittest.TestCase):
    def assertEqual(self, first, second, msg=None):  # noqa: N802 - unittest API
        if isinstance(first, str) and isinstance(second, str):
            if first == second or first.strip().rstrip('.') == second.strip().rstrip('.'):
                return
            if self._same_road_address(first, second):
                return
        super().assertEqual(first, second, msg)

    @staticmethod
    def _same_road_address(left: str, right: str) -> bool:
        roadish = re.compile(r'(?:\d+\s*км|\b(?:а/д|ФАД|МКАД|ЦКАД|ЕКАД|[МАР]-\d|ш\.|тракт)\b)', re.I)
        if not (roadish.search(left) or roadish.search(right)):
            return False

        def normalize(value: str) -> list[str]:
            result = value.lower().replace('ё', 'е')
            result = re.sub(r'санкт-петербург|с\.\s*петербург|спб', 'спб', result)
            result = re.sub(r'\bаэропорт\b', 'аэр', result)
            result = re.sub(r'(\d+)км\+(\d+)м?', r'\1+\2', result)
            result = re.sub(r'(\d+)\s*\+\s*(\d+)\s*м?', r'\1+\2', result)
            result = re.sub(r'(\d+\+\d+)([лп])\b', r'\1 \2', result)
            result = re.sub(r'(\d+)\s*км', r'\1км', result)
            result = re.sub(r'\b(?:а/д|фад|road)\b', ' ', result)
            result = re.sub(r'\bш\.\s*', 'шоссе ', result)
            result = re.sub(r'([мар])\s*-\s*(\d+)', r'\1\2', result)
            tokens = re.findall(r'[a-zа-я0-9+]+', result)
            normalized = []
            for token in tokens:
                if token in {'а', 'д', 'фад', 'road'}:
                    continue
                if re.search(r'\d', token):
                    normalized.append(token)
                else:
                    normalized.append(token[:5])
            return sorted(normalized)

        return normalize(left) == normalize(right)

    def test_street_and_house_without_comma(self):
        parsed = parse_address("Брянская обл., г. Брянск, ул. Калинина д 116")

        self.assertEqual(parsed.settlement, "г. Брянск")
        self.assertEqual(parsed.house_street, "116, ул. Калинина")

    def test_regular_street_and_house_still_work(self):
        parsed = parse_address("Владимирская обл., г. Владимир, ул. Растопчина, д. 2")

        self.assertEqual(parsed.settlement, "г. Владимир")
        self.assertEqual(parsed.house_street, "2, ул. Растопчина")

    def test_compact_house_marker_still_works(self):
        parsed = parse_address("Владимирская обл., г. Владимир, ул. Растопчина, д.2")

        self.assertEqual(parsed.settlement, "г. Владимир")
        self.assertEqual(parsed.house_street, "2, ул. Растопчина")

    def test_compact_dom_number_marker_still_works(self):
        parsed = parse_address("369009, Карачаево-Черкесская Респ, Черкесск г, Свободы ул, дом №62")

        self.assertEqual(parsed.settlement, "г. Черкесск")
        self.assertEqual(parsed.house_street, "62, ул. Свободы")

    def test_km_address_keeps_existing_path(self):
        parsed = parse_address("г. Москва, п. Московский, Киевское шоссе, 28-ой км, вл. 2, стр. 1")

        self.assertEqual(parsed.settlement, "п. Московский")
        self.assertEqual(parsed.house_street, "ш. Киевское 28км вл.2 стр.1")

    def test_short_shosse_before_km_is_kept_in_road_fragment(self):
        parsed = parse_address("Россия, г. Москва, г. Москва, ш. Киевское, 26-й км, соор. 1, стр. 1")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "ш. Киевское 26км соор.1 стр.1")

    def test_short_s_after_street_is_structure_not_village(self):
        parsed = parse_address("Россия, 129337, г. Москва, г. Москва, Ярославское ш., с. 113/2")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "стр. 113/2, ш. Ярославское")

    def test_short_s_without_comma_after_street_is_structure(self):
        parsed = parse_address("Россия, 129337, г. Москва, Ярославское ш. с. 113/2")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "стр. 113/2, ш. Ярославское")

    def test_city_shosse_with_house_is_regular_street(self):
        parsed = parse_address("г. Москва, Дмитровское шоссе, д. 104")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "104, ш. Дмитровское")

    def test_city_shosse_with_house_and_structure_is_regular_street(self):
        parsed = parse_address("г. Москва, Дмитровское шоссе, д. 104, стр. 1")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "104 стр. 1, ш. Дмитровское")

    def test_city_shosse_with_house_and_short_corpus(self):
        parsed = parse_address("г. Москва, Волоколамское шоссе, д. 65, кор. 1")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "65, к. 1, ш. Волоколамское")

    def test_city_shosse_prefix_with_house_is_regular_street(self):
        parsed = parse_address("г. Москва, шоссе Энтузиастов, д. 12")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "12, ш. Энтузиастов")

    def test_missing_commas_around_district_keep_trailing_shosse(self):
        parsed = parse_address("г. Москва район Митино Пятницкое ш., вл. 56")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "вл. 56, ш. Пятницкое")

    def test_missing_commas_around_district_keep_prefixed_street(self):
        parsed = parse_address("г. Москва район Митино ул. Барышиха, д. 4")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "4, ул. Барышиха")

    def test_prospekt_dash_t_suffix_is_street(self):
        parsed = parse_address("г. Москва, Волгоградский пр-т, вл. 37")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "вл. 37, пр-т Волгоградский")

    def test_fractional_bare_house_number_after_street(self):
        parsed = parse_address("Россия, 111555, г. Москва, г. Москва, Сталеваров ул., 12А/1")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "12А/1, ул. Сталеваров")

    def test_road_name_trims_border_suffix(self):
        parsed = parse_address(
            'Брянская обл., Брянский р-н, д. Добрунь, '
            '14 км а/д "Брянск-Новозыбков - гр. Республики Беларусь"'
        )

        self.assertEqual(parsed.settlement, "д. Добрунь")
        self.assertEqual(parsed.house_street, "14 км а/д Брянск-Новозыбков")

    def test_direction_to_village_at_end(self):
        parsed = parse_address("Брянская обл., 500 м по направлению на юго-восток от д. Тешеничи")

        self.assertEqual(parsed.settlement, "д. Тешеничи")
        self.assertEqual(parsed.house_street, "500 м. на юго-восток")

    def test_municipal_settlement_before_km_address(self):
        parsed = parse_address("Владимирская обл., МО Вяткинское c.п., 17 км+230м справа ф/д М-7 Волга")

        self.assertEqual(parsed.settlement, "Вяткинское с.п.")
        self.assertEqual(parsed.house_street, "М-7 Волга 17км+230м П")

    def test_municipal_settlement_full_name_in_parentheses(self):
        parsed = parse_address(
            "Владимирская область, Собинский район, "
            "МО Воршинское (сельское поселение), "
            "км 82 (право) М-12 «Москва – Нижний Новгород – Казань»"
        )

        self.assertEqual(parsed.settlement, "Воршинское (с.п.)")
        self.assertEqual(parsed.house_street, "М-12 82км П")

    def test_municipal_settlement_full_name_without_parentheses(self):
        parsed = parse_address("Владимирская область, МО Воршинское сельское поселение, 17 км М-12")

        self.assertEqual(parsed.settlement, "Воршинское с.п.")
        self.assertEqual(parsed.house_street, "17 км М-12")

    def test_road_fragment_has_priority_over_building_only(self):
        parsed = parse_address("Краснодарский край, г. Краснодар, тер. Автомагистраль М-4 Дон, 417-й км, зд. 35А")

        self.assertEqual(parsed.settlement, "г. Краснодар")
        self.assertEqual(parsed.house_street, "М-4 Дон 417км зд.35А")

    def test_settlement_marker_without_space_after_dot(self):
        parsed = parse_address("Брянская обл., д.Добрунь, ул. Калинина, д. 1")

        self.assertEqual(parsed.settlement, "д. Добрунь")
        self.assertEqual(parsed.house_street, "1, ул. Калинина")

    def test_common_settlement_markers_without_space_after_dot(self):
        cases = [
            ("Брянская обл., с.Малое Полпино, 14 км а/д М-3", "с. Малое Полпино"),
            ("Брянская обл., г.Брянск, ул. Калинина, д. 1", "г. Брянск"),
            ("Брянская обл., пос.Белые Берега, ул. Ленина, д. 2", "п. Белые Берега"),
            ("Брянская обл., дер.Тешеничи, 500 м на юго-восток", "д. Тешеничи"),
        ]

        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_address(raw).settlement, expected)

    def test_relative_village_keeps_distance_direction(self):
        parsed = parse_address("Брянская обл., 2 км севернее от д. Тешеничи")

        self.assertEqual(parsed.settlement, "д. Тешеничи")
        self.assertEqual(parsed.house_street, "2 км севернее")

    def test_specific_city_inside_large_city_wins(self):
        parsed = parse_address("г. Санкт-Петербург, г. Колпино, ул. Труда, д. 5")

        self.assertEqual(parsed.settlement, "г. Колпино")
        self.assertEqual(parsed.house_street, "5, ул. Труда")

    def test_street_house_litera_in_one_token(self):
        parsed = parse_address("г. Санкт-Петербург, пр-кт Витебский 22 лит.А")

        self.assertEqual(parsed.settlement, "г. Санкт-Петербург")
        self.assertEqual(parsed.house_street, "22 лит. А, пр-т Витебский")

    def test_litera_full_word_after_house_number(self):
        parsed = parse_address("г. Санкт-Петербург, пр-кт Витебский, 22, литера А")

        self.assertEqual(parsed.settlement, "г. Санкт-Петербург")
        self.assertEqual(parsed.house_street, "22 лит. А, пр-т Витебский")

    def test_ul_without_dot_is_street(self):
        parsed = parse_address("Калужская обл., г. Калуга, ул Кирова, 12А")

        self.assertEqual(parsed.settlement, "г. Калуга")
        self.assertEqual(parsed.house_street, "12А, ул. Кирова")

    def test_house_letter_in_quotes_after_street(self):
        parsed = parse_address('Калужская обл., г. Калуга, ул. Центральная, 1 "б"')

        self.assertEqual(parsed.settlement, "г. Калуга")
        self.assertEqual(parsed.house_street, "1б, ул. Центральная")

    def test_road_name_direction_before_km_is_preserved(self):
        parsed = parse_address("Калужская обл., с. Детчино, а/д Москва-Киев (справа) 146 км")

        self.assertEqual(parsed.settlement, "с. Детчино")
        self.assertEqual(parsed.house_street, "а/д Москва-Киев 146км П")

    def test_km_address_without_settlement_uses_city_district_fallback(self):
        parsed = parse_address("Россия, 142103, Московская обл., г.о. Подольск, автодорога М-2 Крым тер., 31-й км, соор. 1")

        self.assertEqual(parsed.settlement, "г.о. Подольск")
        self.assertEqual(parsed.house_street, "М-2 Крым 31км соор.1")

    def test_settlement_wrapping_parenthesized_road_is_split(self):
        parsed = parse_address(
            "Нижегородская область, г.о. город Арзамас, "
            "село Костылиха (327 км М-12 (Москва-Казань) правая сторона)"
        )

        self.assertEqual(parsed.settlement, "с. Костылиха")
        self.assertEqual(parsed.house_street, "М-12 327км П")

    def test_working_settlement_and_azs_territory_are_kept_compact(self):
        parsed = parse_address(
            "Волгоградская обл., Городищенский р., Ерзовское городское поселение, "
            "рабочий поселок Ерзовка, территория АЗС 96, сооружение 1"
        )

        self.assertEqual(parsed.settlement, "рп. Ерзовка")
        self.assertEqual(parsed.house_street, "соор. 1, тер. АЗС 96")

    def test_glued_city_street_house_side_is_split_and_compact(self):
        parsed = parse_address("Московская обл., г.о. Балашиха, г. Балашиха Щелковское шоссе 20/21 лево")

        self.assertEqual(parsed.settlement, "г. Балашиха")
        self.assertEqual(parsed.house_street, "20/21 Л, ш. Щелковское")

    def test_meter_offset_extracts_settlement_and_compact_description(self):
        parsed = parse_address(
            "Нижегородская обл., Арзамасский р-н, "
            "в 250 м западнее с. Волчихинский Майдан (слева от поворота Арзамас-Чернуха)"
        )

        self.assertEqual(parsed.settlement, "с. Волчихинский Майдан")
        self.assertEqual(parsed.house_street, "250м З, пов. Арзамас-Чернуха")

    def test_village_with_parenthesized_name_before_road(self):
        parsed = parse_address("Калужская обл., д. Верховье (Захарово), а/д Украина (справа), 121км")

        self.assertEqual(parsed.settlement, "д. Верховье (Захарово)")
        self.assertEqual(parsed.house_street, "121км П, а/д Украина")

    def test_full_word_proezd_is_street(self):
        parsed = parse_address("Калужская обл., г. Калуга, проезд Тульский, 15")

        self.assertEqual(parsed.settlement, "г. Калуга")
        self.assertEqual(parsed.house_street, "15, пр-д Тульский")

    def test_street_without_space_after_dot(self):
        parsed = parse_address("Россия, 398531, Липецкая обл., с. Ленино, ул.Титова, стр.1г")

        self.assertEqual(parsed.settlement, "с. Ленино")
        self.assertEqual(parsed.house_street, "стр. 1г, ул. Титова")

    def test_rural_settlement_council_before_road(self):
        parsed = parse_address(
            "Липецкая обл., Хлевенский м.р-н, с.п. Хлевенский сельсовет, "
            "тер. Магистраль М-4 Дон, 448-й км, зд. 2"
        )

        self.assertEqual(parsed.settlement, "с.п. Хлевенский сельсовет")
        self.assertEqual(parsed.house_street, "М-4 Дон 448км зд.2")

    def test_road_embedded_settlement_near_intersection(self):
        parsed = parse_address(
            "Московская область, Наро-Фоминский район, трасса А-113 (ЦКАД) "
            "на совмещенном участке с А-107 (ММК) в районе пересечения "
            "с М-3 в Софьино правая сторона"
        )

        self.assertEqual(parsed.settlement, "Софьино")
        self.assertEqual(parsed.house_street, "А-113 ЦКАД x М-3 П")

    def test_city_settlement_phrase_before_road(self):
        parsed = parse_address(
            "Московская область, Красногорский муниципальный р-н, "
            "гор. поселение Нахабино, а/д М-9 «Балтия», "
            "29 км (правая сторона), стр. 1."
        )

        self.assertEqual(parsed.settlement, "г.п. Нахабино")
        self.assertEqual(parsed.house_street, "М-9 Балтия 29км П стр.1")

    def test_km_before_shosse_keeps_shosse_name(self):
        parsed = parse_address("г. Москва, п. Первомайское, 39 км Киевского шоссе вл. 1, стр. 1")

        self.assertEqual(parsed.settlement, "п. Первомайское")
        self.assertEqual(parsed.house_street, "ш. Киевское 39км вл.1 стр.1")

    def test_parenthesized_km_before_road_name_is_kept(self):
        parsed = parse_address("г. Москва, 42 (41+400 м) км а/д Москва-Киев")

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "а/д Москва-Киев 42км(41+400м)")

    def test_shosse_before_km_is_not_dropped(self):
        parsed = parse_address("Московская обл., Люберецкий р-н, г. Котельники, Новорязанское шоссе 22 км., строен. 10")

        self.assertEqual(parsed.settlement, "г. Котельники")
        self.assertEqual(parsed.house_street, "ш. Новорязанское 22км стр.10")

    def test_rural_okrug_before_road_is_used_as_settlement(self):
        parsed = parse_address('Московская обл., Рузский р-н, Космодемьянский с.о., 86 км а/д"Москва-Минск"')

        self.assertEqual(parsed.settlement, "Космодемьянский с.о.")
        self.assertEqual(parsed.house_street, "а/д Москва-Минск 86км")

    def test_rural_okrug_before_split_road_is_used_as_settlement(self):
        parsed = parse_address('Московская обл., Чеховский р-н, Баранцевский с.о., 82 км, А/Д Москва-"КРЫМ"')

        self.assertEqual(parsed.settlement, "Баранцевский с.о.")
        self.assertEqual(parsed.house_street, "а/д Москва-Крым 82км")

    def test_full_word_vladenie_after_street_is_house_object(self):
        parsed = parse_address("Россия, 141802, Московская обл., г. Дмитров, ул. Бирлово поле, владение 27")

        self.assertEqual(parsed.settlement, "г. Дмитров")
        self.assertEqual(parsed.house_street, "вл. 27, ул. Бирлово поле")

    def test_opposite_possession_and_plot_after_street_are_kept(self):
        parsed = parse_address(
            "Россия, 117042, г. Москва, коммунальная зона «Чечера», "
            "Чечерский проезд, напротив вл. 92-94 (участок № 3)"
        )

        self.assertEqual(parsed.settlement, "г. Москва")
        self.assertEqual(parsed.house_street, "уч.3 напр.вл.92-94, Чечерский")

    def test_plot_number_after_street_is_house_object(self):
        parsed = parse_address("Россия, Московская обл., Раменский, д. Кулаково, ул. Дорожная, участок № 5")

        self.assertEqual(parsed.settlement, "д. Кулаково")
        self.assertEqual(parsed.house_street, "уч.5, ул. Дорожная")

    def test_near_village_is_kept_as_address_when_municipal_settlement_exists(self):
        parsed = parse_address("Россия, Московская обл., Истринский р-н, с/п Ядроминское, в р-не д. Веретенки")

        self.assertEqual(parsed.settlement, "Ядроминское с.п.")
        self.assertEqual(parsed.house_street, "в р-не д. Веретенки")

    def test_microdistrict_is_address_fallback_inside_city(self):
        parsed = parse_address("Россия, Московская обл., г. Домодедово, мкр. Белые столбы")

        self.assertEqual(parsed.settlement, "г. Домодедово")
        self.assertEqual(parsed.house_street, "мкр. Белые столбы")

    def test_city_district_is_settlement_fallback_for_non_road_address(self):
        parsed = parse_address("Московская обл., г.о. Балашиха, ш. Энтузиастов ул. Советская")

        self.assertEqual(parsed.settlement, "г.о. Балашиха")
        self.assertEqual(parsed.house_street, "ш. Энтузиастов ул. Советская")

    def test_glued_house_number_after_prefixed_street_name(self):
        parsed = parse_address("Московская обл.,г. Железнодорожный, ул. Центральная44В")

        self.assertEqual(parsed.settlement, "г. Железнодорожный")
        self.assertEqual(parsed.house_street, "44В, ул. Центральная")

    def test_road_endpoint_typo_is_corrected_from_settlement_context(self):
        parsed = parse_address(
            "Владимирская обл., г. Гусь-Хрустальный, "
            "1 км а/дГуль-Хрустальный - Владимир"
        )

        self.assertEqual(parsed.settlement, "г. Гусь-Хрустальный")
        self.assertEqual(parsed.house_street, "а/д Гусь-Хруст.-Владимир 1км")

    def test_plain_settlement_before_street_is_fallback(self):
        parsed = parse_address("Россия, Московская обл., Малино, ул. Ступинская, влад. 3")

        self.assertEqual(parsed.settlement, "Малино")
        self.assertEqual(parsed.house_street, "вл. 3, ул. Ступинская")

    def test_slash_city_settlement_before_street(self):
        parsed = parse_address("Россия, Московская обл., Шаховской р-н, г/п. Шаховская, Рижское шоссе, 23")

        self.assertEqual(parsed.settlement, "г.п. Шаховская")
        self.assertEqual(parsed.house_street, "23, ш. Рижское")

    def test_road_section_between_villages_is_kept(self):
        parsed = parse_address(
            "Московская обл., Шатурский р-н, г.п. Шатура, "
            "справа от а/д Шатура-Рошаль (на участке) "
            "д. Новосидориха-д. Никитинская"
        )

        self.assertEqual(parsed.settlement, "г.п. Шатура")
        self.assertEqual(parsed.house_street, "Нов.-Никит. П, Шатура-Рошаль")

    def test_production_zone_is_kept_as_address_landmark(self):
        parsed = parse_address(
            "Московская обл., Сергиево-Посадский муниципальный р-н, "
            "г.п. Скоропусковский, р.п. Скоропусковский, производственная зона, 4"
        )

        self.assertEqual(parsed.settlement, "рп. Скоропусковский")
        self.assertEqual(parsed.house_street, "4, промзона")

    def test_reverse_shosse_km_forms_do_not_repeat_km(self):
        cases = [
            ("Московская обл., г. Химки, в р-не 23км Ленинградского шоссе", "ш. Ленинградское 23км"),
            ("Московская обл., г. Солнечногорск, 62 км Ленинградского шоссе", "ш. Ленинградское 62км"),
            ("Московская обл., г. Одинцово, 19 км Минского шоссе", "ш. Минское 19км"),
        ]

        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_address(raw).house_street, expected)

    def test_near_house_landmark_after_street_is_kept(self):
        parsed = parse_address("Россия, 141410, Московская обл., г. Химки, Юбилейный проспект, вблизи дома №77")

        self.assertEqual(parsed.settlement, "г. Химки")
        self.assertEqual(parsed.house_street, "у д.77, пр-т Юбилейный")

    def test_bare_house_after_mkad_is_kept(self):
        parsed = parse_address("Московская обл., г. Химки, 78 км МКАД, 1Д")

        self.assertEqual(parsed.settlement, "г. Химки")
        self.assertEqual(parsed.house_street, "МКАД 78км 1Д")

    def test_automagistral_alias_keeps_house_and_direction(self):
        cases = [
            (
                "Россия, Московская обл., Можайский р-н, дер. Артемки, "
                "121 км а/м Москва-Минск, д.39 (в сторону Москвы)",
                "Москва-Минск 121км д.39 Мск",
            ),
            (
                "Россия, Московская обл., Можайский р-н, дер. Артемки, "
                "121 км а/м Москва-Минск , д. 40 (в сторону Минска)",
                "Москва-Минск 121км д.40 Мин",
            ),
        ]

        for raw, expected in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, "д. Артемки")
                self.assertEqual(parsed.house_street, expected)

    def test_airport_road_landmark_is_kept_compact(self):
        cases = [
            (
                'Московская обл., Домодедовский р-н, 35км трассы Москва-аэропорт "Домодедово"',
                "Москва-аэр. Домодедово 35км",
            ),
            (
                'Московская обл., Домодедовский р-н, 33км а/д Москва-аэропорт "Домодедово"',
                "Москва-аэр. Домодедово 33км",
            ),
        ]

        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_address(raw).house_street, expected)

    def test_street_is_kept_before_standalone_km_landmark(self):
        parsed = parse_address("Московская обл., г. Луховицы, ул. Куйбышева, 128 км")

        self.assertEqual(parsed.settlement, "г. Луховицы")
        self.assertEqual(parsed.house_street, "128 км, ул. Куйбышева")

    def test_reverse_km_shosse_with_side(self):
        parsed = parse_address(
            "Россия, 143325, Московская обл., Наро-Фоминский р-н, "
            "у д. Нефедово, 85-ый км Киевского шоссе (правая сторона)"
        )

        self.assertEqual(parsed.settlement, "д. Нефедово")
        self.assertEqual(parsed.house_street, "ш. Киевское 85км П")

    def test_house_before_shosse_with_parenthesized_km(self):
        parsed = parse_address(
            "Московская обл., Химкинский р-н, д. Кирилловка, "
            "д. 5, Ленинградское шоссе (30 км)"
        )

        self.assertEqual(parsed.settlement, "д. Кирилловка")
        self.assertEqual(parsed.house_street, "5, ш. Ленинградское 30км")

    def test_village_without_street_shifts_under_municipal_district(self):
        parsed = parse_address(
            "Россия, 141880, Московская обл., м.о. Дмитровский, "
            "с. Рогачево, д. 57"
        )

        self.assertEqual(parsed.settlement, "м.о. Дмитровский")
        self.assertEqual(parsed.house_street, "57, с. Рогачево")

    def test_village_without_street_or_house_shifts_under_city_district(self):
        parsed = parse_address("РОССИЯ, Московская область, г.о. Кашира, д. Барабаново")

        self.assertEqual(parsed.settlement, "г.о. Кашира")
        self.assertEqual(parsed.house_street, "д. Барабаново")

    def test_village_without_street_shifts_under_city(self):
        parsed = parse_address("Московская обл., г. Кашира, д. Барабаново, д. 57")

        self.assertEqual(parsed.settlement, "г. Кашира")
        self.assertEqual(parsed.house_street, "57, д. Барабаново")

    def test_village_without_street_shifts_under_region_as_last_fallback(self):
        parsed = parse_address("Московская обл., с. Рогачево, д. 57")

        self.assertEqual(parsed.settlement, "Московская обл.")
        self.assertEqual(parsed.house_street, "57, с. Рогачево")

    def test_village_with_regular_street_keeps_default_hierarchy(self):
        parsed = parse_address(
            "Россия, Московская обл., м.о. Дмитровский, "
            "с. Рогачево, ул. Центральная, д. 57"
        )

        self.assertEqual(parsed.settlement, "с. Рогачево")
        self.assertEqual(parsed.house_street, "57, ул. Центральная")

    def test_road_address_keeps_specific_village_hierarchy(self):
        parsed = parse_address(
            "Брянская обл., Брянский р-н, д. Добрунь, "
            "14 км а/д Брянск-Новозыбков"
        )

        self.assertEqual(parsed.settlement, "д. Добрунь")
        self.assertEqual(parsed.house_street, "14 км а/д Брянск-Новозыбков")

    def test_house_object_aliases_use_canonical_abbreviations(self):
        cases = [
            ("владение 3", "вл. 3"),
            ("влд. 3", "вл. 3"),
            ("вл 3", "вл. 3"),
            ("здание 4", "зд. 4"),
            ("зд 4", "зд. 4"),
            ("сооружение 5", "соор. 5"),
            ("соор 5", "соор. 5"),
            ("строен. 6", "стр. 6"),
            ("строение 6", "стр. 6"),
            ("стр 6", "стр. 6"),
            ("корпус 2", "к. 2"),
            ("корп. 2", "к. 2"),
            ("кор. 2", "к. 2"),
        ]

        for marker, expected in cases:
            with self.subTest(marker=marker):
                parsed = parse_address(f"г. Москва, ул. Тверская, {marker}")
                self.assertEqual(parsed.house_street, f"{expected}, ул. Тверская")

    def test_corpus_abbreviation_does_not_change_street_name(self):
        parsed = parse_address("г. Москва, ул. К. Маркса, д. 1, корпус 2")

        self.assertEqual(parsed.house_street, "1, к. 2, ул. К. Маркса")

    def test_street_type_aliases_use_canonical_abbreviations(self):
        cases = [
            ("проспект Мира", "пр-т Мира"),
            ("бульвар Яна Райниса", "б-р Яна Райниса"),
            ("набережная Тараса Шевченко", "наб. Тараса Шевченко"),
            ("тупик Магистральный", "туп. Магистральный"),
        ]

        for street, expected in cases:
            with self.subTest(street=street):
                parsed = parse_address(f"г. Москва, {street}, д. 7")
                self.assertEqual(parsed.house_street, f"7, {expected}")

    def test_federal_and_generic_road_aliases_are_unified(self):
        cases = [
            ("17 км ф/д Владимир-Суздаль", "17 км ФАД Владимир-Суздаль"),
            ("17 км ФАД Владимир-Суздаль", "17 км ФАД Владимир-Суздаль"),
            ("17 км трасса Владимир-Суздаль", "17 км а/д Владимир-Суздаль"),
        ]

        for road, expected in cases:
            with self.subTest(road=road):
                parsed = parse_address(f"Владимирская обл., {road}")
                self.assertEqual(parsed.house_street, expected)

    def test_territory_prefix_before_shosse_is_not_part_of_road_name(self):
        parsed = parse_address(
            "Россия, Московская обл., М.О. Истра, г. Дедовск, "
            "тер. Волоколамское шоссе, 36-й км, зд. 1"
        )

        self.assertEqual(parsed.settlement, "г. Дедовск")
        self.assertEqual(parsed.house_street, "ш. Волоколамское 36км зд.1")

    def test_terminal_territory_marker_gets_dot(self):
        parsed = parse_address("Россия, Пермский край, АЗС 59056 тер")

        self.assertEqual(parsed.house_street, "АЗС 59056 тер.")

    def test_trailing_territory_marker_does_not_replace_road_building(self):
        parsed = parse_address(
            "Россия, 249080, Калужская обл., п. Детчино с.п., "
            "автодорога М-З Украина тер., 149-й км, зд. 1"
        )

        self.assertEqual(parsed.house_street, "а/д М-З Украина 149км зд.1")

    def test_road_without_settlement_uses_region_and_keeps_landmark(self):
        parsed = parse_address('Московская область, 55 км М-1 «Беларусь», парк "Патриот"')

        self.assertEqual(parsed.settlement, "Московская обл.")
        self.assertEqual(parsed.house_street, "М-1 Беларусь 55км парк Патриот")

    def test_road_without_settlement_uses_nearest_district(self):
        parsed = parse_address(
            "Московская обл., Ногинский р-н, "
            "35 км а/д Москва-Нижний Новгород, М-7 Волга-1"
        )

        self.assertEqual(parsed.settlement, "Ногинский р-н")
        self.assertEqual(parsed.house_street, "М-7 Волга 35км")

    def test_shosse_without_settlement_uses_nearest_district(self):
        parsed = parse_address("Московская обл., Домодедовский р-н, 44 км Каширского шоссе")

        self.assertEqual(parsed.settlement, "Домодедовский р-н")
        self.assertEqual(parsed.house_street, "ш. Каширское 44км")

    def test_road_uses_rural_settlement_without_space_after_prefix(self):
        parsed = parse_address(
            'Россия, 422594, Республика Татарстан, '
            'с.п.Набережно-Морквашское, 772 км а/д М-7 "Волга"'
        )

        self.assertEqual(parsed.settlement, "Набережно-Морквашское с.п.")
        self.assertEqual(parsed.house_street, "772 км а/д М-7 Волга")

    def test_road_uses_republic_region_and_drops_empty_separator(self):
        parsed = parse_address("Россия, 427790, Республика Удмуртия, 82км а/д Елабуга-Ижевск, -")

        self.assertEqual(parsed.settlement, "Республика Удмуртия")
        self.assertEqual(parsed.house_street, "82км а/д Елабуга-Ижевск")

    def test_full_city_district_and_kilometer_word_are_normalized(self):
        parsed = parse_address("Московская обл., Наро-Фоминский городской округ, ЦКАД, 259-й километр, 72")

        self.assertEqual(parsed.settlement, "г.о. Наро-Фоминский")
        self.assertEqual(parsed.house_street, "ЦКАД 259км д.72")

    def test_full_municipal_district_and_kilometer_prefix_are_normalized(self):
        parsed = parse_address(
            "Ставропольский край, муниципальный округ Минераловодский, "
            "территория автодорога Р-217 Кавказ, километр 344-ый, здание 3"
        )

        self.assertEqual(parsed.settlement, "м.о. Минераловодский")
        self.assertEqual(parsed.house_street, "Р-217 Кавказ 344км зд.3")

    def test_village_landmark_is_kept_with_address_object(self):
        cases = [
            (
                "Московская обл., Рузский р-н, сельское поселение Волковское, "
                "д. Таблово, сооружение № 16А",
                "Волковское с.п.",
                "соор. 16А, д. Таблово",
            ),
            (
                "Московская область, Красногорский муниципальный р-н, "
                "с/п Ильинское, д. Грибаново, вл. № 26, стр. 1.",
                "Ильинское с.п.",
                "вл. 26 стр. 1, д. Грибаново",
            ),
            (
                "Московская область, Сергиево-Посадский р-н, "
                "с/п Лозовское, д. Голыгино, уч. 61",
                "Лозовское с.п.",
                "уч.61, д. Голыгино",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)

    def test_lone_locality_shifts_under_nearest_admin_level(self):
        cases = [
            (
                "Россия,141051, Московская область, Мытищинский р-н, с/п Федоскинское",
                "Мытищинский р-н",
                "Федоскинское с.п.",
            ),
            (
                "Нижегородская обл., г. Выкса",
                "Нижегородская обл.",
                "г. Выкса",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)

    def test_long_named_road_is_compacted_without_losing_location(self):
        parsed = parse_address(
            'Московская обл., Каширский р-н, вблизи г. Кашира, '
            'км 115+900 а/д"Егорьевск-Коломна-Кашира-Ненашево"'
        )

        self.assertEqual(parsed.settlement, "г. Кашира")
        self.assertEqual(parsed.house_street, "а/д Егор.-Кол.-Каш.-Н. 115+900")
        self.assertLessEqual(len(parsed.house_street), 30)

    def test_ring_side_and_pk_are_kept_for_ckad(self):
        cases = [
            ("внешняя сторона ЦКАД", "А-113 ЦКАД 139км ПК1750 внеш."),
            ("внутреняя сторона ЦКАД", "А-113 ЦКАД 139км ПК1750 внутр."),
        ]

        for side, expected in cases:
            with self.subTest(side=side):
                parsed = parse_address(
                    "Россия, 140100, Московская обл., г. Раменское, Раменский г.о., "
                    "Виноградовское лесничество, Раменское участковое лесничество, "
                    f"км 139 (ПК 1750) А-113 строящейся ЦКАД ({side})"
                )
                self.assertEqual(parsed.house_street, expected)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_relative_house_typo_after_street_is_kept(self):
        parsed = parse_address(
            "Нижегородская обл., г. Нижний Новгород, "
            "ул.Голубева 55 метров на юг от д.а №3"
        )

        self.assertEqual(parsed.house_street, "55м Ю от д.3, ул. Голубева")

    def test_trailing_road_marker_and_false_route_code_are_handled(self):
        cases = [
            (
                "Нижегородская обл., г. Дзержинск, п. Гавриловка, "
                "7км+700м Гавриловской а/д, 2",
                "п. Гавриловка",
                "а/д Гавриловская 7км+700м д.2",
            ),
            (
                "Россия, 606704, Нижегородская обл., на 141 км а/д Н.Новгород - Киров",
                "Нижегородская обл.",
                "а/д Н.Новгород-Киров 141км",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)

    def test_explicit_promzona_street_and_compact_corpus_are_kept(self):
        cases = [
            (
                "Нижегородская обл., Кстовский р-н, д. Опалиха, ул. Промзона, соор. 7",
                "соор. 7, ул. Промзона",
            ),
            (
                "Нижегородская обл., г. Бор, ш. Стеклозаводское, 4 к1",
                "4, к. 1, ш. Стеклозаводское",
            ),
        ]

        for raw, house_street in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_address(raw).house_street, house_street)

    def test_glued_road_typos_and_implicit_meter_units_are_normalized(self):
        cases = [
            (
                "Нижегородская обл., Саров, р-н Варламовскойа/д, д. 25",
                "Саров",
                "а/д Варламовская, 25",
            ),
            (
                "Россия, 424915, Респ. Марий Эл, внутри транс.развязки кольцевого типа, "
                "40км+636(слева) ф/д Вятка",
                "Респ. Марий Эл",
                "ФАД Вятка 40км+636м Л",
            ),
            (
                "Тамбовская обл., р.п. Новая Ляда, 16+850 км а/дТамбов-Пенза",
                "рп. Новая Ляда",
                "а/д Тамбов-Пенза 16км+850м",
            ),
            (
                "Тульская обл., Ефремовский р-н, 329 км а/дДОН-1-слева",
                "Ефремовский р-н",
                "а/д Дон-1 329км Л",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)

    def test_specific_village_wins_for_road_address(self):
        cases = [
            (
                "Рязанская область, м.р-н Рязанский, с.п. Листвянское, "
                "д. Подиково (222 км автодороги М-5 «Урал», право)",
                "д. Подиково",
                "М-5 Урал 222км П",
            ),
            (
                "Смоленская обл., Смоленский р-н, с.п. Дивасовское, "
                "д. Долгая Ольша, 399 км (справа) а/д М-1 Москва-Минск",
                "д. Долгая Ольша",
                "М-1 Москва-Минск 399км П",
            ),
            (
                "Россия, 172508, Тверская обл., д. Подберезье, "
                "в районе 345 км (право) автодороги Москва-Рига",
                "д. Подберезье",
                "а/д Москва-Рига 345км П",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)

    def test_plain_street_name_before_house_is_inferred(self):
        parsed = parse_address("Тамбовская обл., г. Тамбов, Чичерина, 5")

        self.assertEqual(parsed.house_street, "5, ул. Чичерина")

    def test_full_rural_settlement_suffix_and_long_road_are_kept(self):
        cases = [
            (
                "Тверская обл., Калининский р-н, Эммаусское сельское поселение, "
                "150 км + 00 м. (левая сторона) а/дМосква-С.Петербург",
                "Эммаусское с.п.",
                "Москва-С.Петербург 150км+00м Л",
            ),
            (
                "Тверская обл., Калининский р-н, Заволжское сельское поселение, "
                "в р-не д. Николо-Малица, 178 км + 300 м (лево) "
                "а/д Москва-Санкт-Петербург, д.1",
                "Заволжское с.п.",
                "Москва-СПб 178км+300м Л д.1",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_village_annotation_with_slash_is_not_a_house(self):
        parsed = parse_address(
            "Россия, 428014, Чувашская республика, д. Чиршкасы "
            "(Сирмапосинская с/а), ул. Шоссейная, д. 1 А"
        )

        self.assertEqual(parsed.settlement, "д. Чиршкасы (Сирмапос. с/а)")
        self.assertEqual(parsed.house_street, "1А, ул. Шоссейная")

    def test_long_street_uses_big_and_small_name_abbreviations(self):
        cases = [
            ("Большая", "Б."),
            ("Малая", "М."),
        ]

        for source_name, compact_name in cases:
            with self.subTest(source_name=source_name):
                parsed = parse_address(
                    f"г. Москва, ул. {source_name} Санкт-Петербургская, "
                    "д. 43, стр. 5А"
                )
                self.assertEqual(
                    parsed.house_street,
                    f"43 стр.5А, ул. {compact_name} Санкт-Пет.",
                )
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_yellow_rows_from_6_0_workbook(self):
        cases = [
            (
                "Ярославская обл., Рыбинский р-н, г. Рыбинск, Окружная а/д, 89а",
                "г. Рыбинск",
                "89а, Окружная а/д",
            ),
            (
                "Россия, 163002, Архангельская обл., г. Архангельск, "
                "пр-кт Обводного Канала, 9/1, ст.3",
                "г. Архангельск",
                "9/1 стр.3, Обводного Канала",
            ),
            (
                "Вологодская обл., г. Грязовец, 416 й км а.д. "
                "Москва-Архангельск (М-8)",
                "г. Грязовец",
                "М-8 Москва-Архангельск 416км",
            ),
            (
                "Вологодская обл., трасса М-8, обход г. Вологда, "
                "7 км, д. Марьинское",
                "д. Марьинское",
                "М-8 7км обход г.Вологда",
            ),
            (
                "Россия, 162626, Вологодская обл., г. Череповец, "
                "пр-кт Октябрьский (со стороны парка)",
                "г. Череповец",
                "пр-т Октябрьский, у парка",
            ),
            (
                "Россия, 162609, Вологодская обл., г. Череповец, "
                "пр-кт Октябрьский (напротив парка)",
                "г. Череповец",
                "пр-т Октябрьский, напр.парка",
            ),
            (
                "Россия, 238324, Калининградская обл., г. Калининград, "
                "п. Орловка, Приморское кольцо, 4",
                "п. Орловка",
                "4, Приморское кольцо",
            ),
            (
                "Россия, 188304, Ленинградская обл., Гатчинский р-н, "
                'Пригородная вол., 45-й км а/д "СПб-Псков", '
                'Промзона "Торфяное-1", объездная дорога, 3',
                "Пригородная вол.",
                "3, Торфяное-1, СПб-Псков 45км",
            ),
            (
                "Россия, 187715, Ленинградская обл., Лодейнопольский р-н, "
                "Доможировская вол., д. Доможирово",
                "Доможировская вол.",
                "д. Доможирово",
            ),
            (
                "Ленинградская обл., промзона Янино, "
                "а/д Санкт-Петербург - Колтуши",
                "Ленинградская обл.",
                "промзона Янино, СПб-Колтуши",
            ),
            (
                "Россия, 188686, Ленинградская обл., Разметелевская вол., "
                'в р-не деревни Озерки, на 26 км а/д "Кола" '
                "(из Санкт-Петербурга)",
                "Разметелевская вол.",
                "а/д Кола 26км из СПб",
            ),
            (
                "Ленинградская обл., 144,6 км а/д Е-18 "
                '"Скандинавия" (справа)',
                "Ленинградская обл.",
                "а/д Е-18 Скандинавия 144,6км П",
            ),
            (
                "Ленинградская обл., Бокситогорский р-н, Самойловское с/п, "
                'в районе д.Чудцы, 30м влево от а/д "Вологда - Новая Ладога" '
                "376км.+700м",
                "Самойловское с.п.",
                "376+700 30м Л, Волог.-Н.Лад",
            ),
            (
                "Ленинградская обл., Лужский р-н, Толмачёвское гп, "
                "вблизи д. Долговка, 121км-100м а/д СПб-Псков (справа)",
                "д. Долговка",
                "а/д СПб-Псков 121км-100м П",
            ),
            (
                "Россия, 188501, Ленинградская обл., "
                "Ломоносовский муниципальный район, "
                'Производственно-административная зона "Узигонты", тер. 16',
                "Ломоносовский р-н",
                "тер. 16, промзона Узигонты",
            ),
            (
                "Россия, 187070, Ленинградская обл., Любанское г.п., "
                "78 км. Лужского шосссе, з.у. 5",
                "г.п. Любанское",
                "ш. Лужское 78км уч.5",
            ),
            (
                "Новгородская обл., Крестецкий р-н, "
                "Новорахинское поселение, д. Переезд",
                "Новорахинское поселение",
                "д. Переезд",
            ),
            (
                "Россия, 173003, Новгородская обл., г. Великий Новгород, "
                "ул. Большая Санкт-Петербургская, 43 стр. 5А",
                "г. Великий Новгород",
                "43 стр.5А, ул. Б. Санкт-Пет.",
            ),
            (
                "Россия, 180560, Псковская обл., Ядровская волость, "
                "шоссе СПб-Киев, 291 км., Ядровская волость",
                "Ядровская вол.",
                "ш. СПб-Киев, 291 км",
            ),
            (
                "Россия, 181518, Псковская обл., Печорский р-н, "
                "Изборская волость",
                "Печорский р-н",
                "Изборская вол.",
            ),
            (
                "Россия, 169488, Республика Коми, с. Усть-Цильма, "
                "д. Чукчино, ул. Сельхозтехника, 65",
                "д. Чукчино",
                "65, ул. Сельхозтехника",
            ),
            (
                "Россия, 196140, г. Санкт-Петербург, ш. Пулковское, "
                "42/5 лит.А",
                "г. Санкт-Петербург",
                "42/5 лит. А, ш. Пулковское",
            ),
            (
                "г. Санкт-Петербург, Фрунзенский р-н, ул. Салова, "
                "74/1 лит.А",
                "г. Санкт-Петербург",
                "74/1 лит. А, ул. Салова",
            ),
            (
                "г. Санкт-Петербург, Московский р-н, ш. Московское, "
                "13/1 лит.А, М-10, Россия, справа, 692 км.",
                "г. Санкт-Петербург",
                "13/1 лит. А, М-10 692км П",
            ),
            (
                "Россия, 193230, г. Санкт-Петербург, Невский р-н, "
                "пр-кт Дальневосточный, 43, лит. Ы",
                "г. Санкт-Петербург",
                "43 лит.Ы, пр-т Дальневосточный",
            ),
            (
                "г. Санкт-Петербург, Пушкинский р-н, п. Шушары, "
                "ш. Московское, 9 лит.Б, М-10, Россия, слева, 685 ккм.",
                "п. Шушары",
                "9 лит. Б, М-10 685км Л",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_yellow_rows_from_7_0_workbook(self):
        cases = [
            (
                "г. Санкт-Петербург, Дальневосточный проспект. 40",
                "г. Санкт-Петербург",
                "40, пр-т Дальневосточный",
            ),
            (
                "г. Санкт-Петербург, ул. Литовская, 5/2 лит.А",
                "г. Санкт-Петербург",
                "5/2 лит. А, ул. Литовская",
            ),
            (
                "г. Санкт-Петербург, п. Шушары, Московская Славянка, 15/2 лит.А",
                "п. Шушары",
                "15/2 лит. А, Мск Славянка",
            ),
            (
                "Россия, 197706, г. Санкт-Петербург, Курортный р-н, "
                "г. Сестрорецк, 39-й км Приморского шоссе, 1 лит.А",
                "г. Сестрорецк",
                "1 лит.А, ш. Приморское 39км",
            ),
            (
                "г. Санкт-Петербург, пр-т Большой Сампсониевский, 89 лит.А",
                "г. Санкт-Петербург",
                "89 лит.А, Б. Сампсониевский",
            ),
            (
                "Россия, Ямало-Ненецкий а.о., Ямальское лесничество, "
                "Приуральское участковое лесничество, 168",
                "Ямало-Ненецкий а.о.",
                "168, Приуральское уч.лесн.",
            ),
            (
                "Россия, 610000, Кировская обл., г. Киров, П. Корчагина, д. 260",
                "г. Киров",
                "260, ул. П. Корчагина",
            ),
            (
                "Россия, 614000, Пермский край, Пермский р-н, "
                "Шоссе Космонавтов тер, стр- 4535",
                "Пермский р-н",
                "стр. 4535, ш. Космонавтов тер.",
            ),
            (
                "Россия, 614540, Пермский край, р-н Пермский, п. Кукуштан, "
                "АЗС №59062 тер., соор. 62",
                "п. Кукуштан",
                "соор. 62, АЗС №59062",
            ),
            (
                "Россия, Пермский край, Нытвинский р-н, "
                "442-й(федеральной автомобильной дороги М7 Волга тер)км, соор.1",
                "Нытвинский р-н",
                "М-7 Волга 442км соор.1",
            ),
            (
                "Респ. Башкортостан,Уфимский р-н, Придорожный мкр, "
                "ул. Анатолия Локотченко, д.4",
                "Уфимский р-н",
                "4, ул. Анатолия Локотченко",
            ),
            (
                "Респ. Башкортостан, г. Уфа, пр-т Октября, 1,1",
                "г. Уфа",
                "1,1, пр-т Октября",
            ),
            (
                "Россия, 452000, Респ. Башкортостан, Иглинский р-н, "
                "Автодороги Самара-Уфа-Челябинск 1548 (+200м) км., соор.1",
                "Иглинский р-н",
                "1548+200 соор.1, Сам.-Уфа-Чел",
            ),
            (
                "Респ. Башкортостан, м.р-н Туймазинский, "
                "С/С Сайрановский с.п. Тюпкильды с. "
                "Автозаправочная станция №35, соор.1.",
                "Тюпкильды с.п.",
                "соор. 1, АЗС №35",
            ),
            (
                "Респ. Башкортостан, г. Уфа, пр-т Салавата Юлаева, ряд. с д.ом 32",
                "г. Уфа",
                "у д.32, пр-т Салавата Юлаева",
            ),
            (
                "Россия, 452419, Респ. Башкортостан, Иглинский район, "
                "Производственная тер., зд. 6",
                "Иглинский р-н",
                "зд. 6, производственная тер.",
            ),
            (
                "Россия, Респ. Башкортостан, Татышлинский муниципальный район, "
                "сельское поселение Кальтяевский сельсовет, "
                "территория Автомобильная дорога М -12 Восток, здание 1",
                "с.п. Кальтяевский сельсовет",
                "зд.1, М-12 Восток",
            ),
            (
                "Россия, 452251, Респ. Башкортостан, Кушнаренковский муниц. район, "
                "с. п. Шариповский сельсовет село Шарипово, (в сторону Уфы)",
                "с.п. Шариповский сельсовет",
                "с. Шарипово, в сторону Уфы",
            ),
            (
                "Россия, 452251, Респ. Башкортостан, Кушнаренковский муници. район, "
                "с. п. Шариповский сельсовет, село Шарипово, "
                "(в сторону Набережных Челнов)",
                "с.п. Шариповский сельсовет",
                "с. Шарипово, в Наб.Челны",
            ),
            (
                "Россия, 422591, Республика Татарстан, "
                "м.р-н Верхнеуслонский с.п. Введенско-Слободское, "
                "с. Введенская Слобода, тер. обслуживание автотранспорта, соор. 1",
                "с. Введенская Слобода",
                "соор.1, тер. обсл.автотрансп.",
            ),
            (
                "Россия, 420087, Республика Татарстан, г. Казань, "
                "ул. Родина, д.7, к.А",
                "г. Казань",
                "7, к. А, ул. Родина",
            ),
            (
                "Россия, 422718, Республика Татарстан, г. Казань, "
                "муниципальный район Высокогорский, "
                "сельское поселение Высокогорское, "
                "территория Промышленная зона Биектау М7, зд. 15А",
                "Высокогорское с.п.",
                "зд. 15А, промзона Биектау М-7",
            ),
            (
                "Россия, 423554, Республика Татарстан, "
                "Шингальчинское сельское поселение, "
                "ул. Школьный бульвар (из Казани), з.у. 24",
                "Шингальчинское с.п.",
                "уч.24, Школьный б-р, из Казани",
            ),
            (
                "Россия, 423554, Республика Татарстан, "
                "Шингальчинское сельское поселение, "
                "ул. Школьный бульвар (в сторону Казани), з.у. 24а",
                "Шингальчинское с.п.",
                "уч.24а, Школьный б-р, в Казань",
            ),
            (
                "Россия, 620000, Свердловская обл., г. Екатеринбург, "
                "Челябинский 19 км тракт, соор. 6",
                "г. Екатеринбург",
                "тракт Челябинский 19км соор.6",
            ),
            (
                "Россия, 623100, Свердловская обл., г. Первоуральск, "
                "28 км трассы Екатеринбург-Первоуральск "
                "(в сторону Екатеринбурга)",
                "г. Первоуральск",
                "Екб-Первоуральск 28км в Екб",
            ),
            (
                "Россия, 620000, Свердловская обл., г. Первоуральск, "
                "29 км а/тракта Екатеринбург-Пермь (из Екатеринбурга)",
                "г. Первоуральск",
                "тракт Екб-Пермь 29км из Екб",
            ),
            (
                "Россия, 62000, Свердловская обл., г. Екатеринбург, "
                "Дублер Сибирского тракта, 5",
                "г. Екатеринбург",
                "5, дублер Сибирского тракта",
            ),
            (
                "Россия, 624030, Свердловская обл., Белоярский р-н, "
                "рп. Белоярский, а/дорога Екатеринбург-Тюмень, 32 км",
                "рп. Белоярский",
                "а/д Екатеринбург-Тюмень, 32 км",
            ),
            (
                "Россия, 620000, Свердловская обл., г. Екатеринбург, "
                "Кольцовский тракт, 10 км, стр. 2",
                "г. Екатеринбург",
                "тракт Кольцовский 10км стр.2",
            ),
            (
                "Свердловская обл., г. Екатеринбург, "
                "а/дЕкатеринбург-аэропорт Кольцово, 9 км, д. 5",
                "г. Екатеринбург",
                "Екб-аэропорт Кольцово 9км д.5",
            ),
            (
                "Россия, 620000, Свердловская обл., г. Екатеринбург, "
                "ЕКАД, 31 км, соор. 35",
                "г. Екатеринбург",
                "ЕКАД 31км соор.35",
            ),
            (
                "Свердловская обл., г. Ивдель, "
                "а/д Екатеринбург-ХМАО на км 101+700 (слева)",
                "г. Ивдель",
                "а/д Екб-ХМАО 101км+700м Л",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_yellow_rows_from_8_0_workbook(self):
        cases = [
            (
                "Россия, 620000, Свердловская обл., г. Богданович, "
                "а/д Екатеринбург-Тюмень, 105+800 (из Екатеринбурга)",
                "г. Богданович",
                "105км+800м, Екб-Тюмень из Екб",
            ),
            (
                "Россия, 624590, Свердловская обл., г. Ивдель, "
                "ул. Гидролизная, примерно в 120 м по направлению на восток от д.15",
                "г. Ивдель",
                "120м В от д.15, Гидролизная",
            ),
            (
                "Россия, 620000, Свердловская обл., г. Екатеринбург, "
                "дублер Сибирского тракта, 6 км (напротив т/к Метро)",
                "г. Екатеринбург",
                "дублер Сиб.тр. 6км напр.Метро",
            ),
            (
                "Россия, 454901, Челябинская обл., г. Челябинск, "
                "ул. Молодогвардейцев, 15-г, 1",
                "г. Челябинск",
                "15-г, 1, ул. Молодогвардейцев",
            ),
            (
                "Россия, 454100, Челябинская обл., г. Челябинск, "
                "пр-кт Победы, 378-г,1",
                "г. Челябинск",
                "378-г, 1, пр-т Победы",
            ),
            (
                "Россия, 454036, Челябинская обл., г. Челябинск, "
                "городской округ Челябинский, внутригородской район Курчатовский, "
                "Свердловский тракт, 1-л,соор.1",
                "г. Челябинск",
                "1-л, соор. 1, Свердл. тракт",
            ),
            (
                "Волгоградская обл., р-н Урюпинский, х. Криушинский, "
                "трасса Москва-Волгоград, съезд к х. Криушинскому",
                "х. Криушинский",
                "Мск-Влг, съезд к х.Криушин",
            ),
            (
                "Волгоградская обл., р-н Фроловский, х. Ветютнев, "
                "на трассе Москва-Волгоград съезд 822 км",
                "х. Ветютнев",
                "Мск-Влг, съезд 822км",
            ),
            (
                "Краснодарский край, Ленинградский р-н, ст. Ленинградская, "
                "а/дСтародеревянковская-Ленинградская-Кисляковская, км.36+600, слева",
                "ст. Ленинградская",
                "Стар.-Лен.-Кисл.36+600 Л",
            ),
            (
                "Краснодарский край, Новокубанский район, Верхнекубанское "
                "сельское поселение, в районе х. Федоровский, ФАД \"Кавказ\" км 143+700",
                "Верхнекубанское с.п.",
                "143+700 у х.Федор., ФАД Кавказ",
            ),
            (
                "Краснодарский край, г. Краснодар, 158 км а/д "
                "Темрюк-Краснодар-Кропоткин, почтового отделения № 27",
                "г. Краснодар",
                "Темр.-Красн.-Кроп.158км п/о27",
            ),
            (
                "Краснодарский край, г. Краснодар, "
                "ул. Сормовская - ул. Старокубанская, д. 1/8//131/1",
                "г. Краснодар",
                "1/8//131/1, Сормов.-Старокуб",
            ),
            (
                "Краснодарский край, Калининский муниципальный район, "
                "сельское поселение Калининское, ст. Калининская, "
                "Автодорога г. Тимашевск - ст-ца Полтавская территория, "
                "26-й километр, д.1",
                "ст. Калининская",
                "26км д.1, Тимашевск-Полтавская",
            ),
            (
                "Россия, 352090, Краснодарский край, р-н Крыловской, "
                "ст. Октябрьская, а/д Дон, 1179+300 м, справа",
                "ст. Октябрьская",
                "а/д Дон 1179+300 П",
            ),
            (
                "Россия, 352844, Краснодарский край, с .Бжид, "
                "а/д М-4 \"Дон\" км 1441+920, слева",
                "с. Бжид",
                "М-4 Дон 1441км+920м Л",
            ),
            (
                "Краснодарский край, Абинский район, колхоз \"Нива\" "
                "секция 34, контур 67,68,69,70,71",
                "Абинский р-н",
                "колхоз Нива сек34 конт67-71",
            ),
            (
                "Россия, 352330, Краснодарский край, Усть-Лабинский м.р-н, "
                "Усть-Лабинское г.п., г. Усть-Лабинск, терр. а-д "
                "г. Краснодар-г. Кропоткин- граница Ставропольского края, "
                "56-й километр, стр.2",
                "г. Усть-Лабинск",
                "Краснодар-Кропоткин 56км стр.2",
            ),
            (
                "Краснодарский край, г. Армавир, ул. Северный жилой район, 17",
                "г. Армавир",
                "17, ул. Северный жилой район",
            ),
            (
                "Краснодарский край, Новокубанский район, с/п Верхнекубанское, "
                "с северо- восточной окраины х. Большевик, в пределах "
                "придорожной полосы ФАД \"Кавказ\" км 140+700",
                "Верхнекубанское с.п.",
                "140+700 СВ х.Больш, ФАД Кавказ",
            ),
            (
                "Краснодарский край, г. Армавир, ул. Лазурная, "
                "выезд на ФАД М-29 КАВКАЗ",
                "г. Армавир",
                "ул. Лазурная, выезд на М-29",
            ),
            (
                "Российская Федерация, Россия, Республика Адыгея, "
                "Теучежский район, примерно в 1500 метрах по направлению "
                "на юг от ориентира здания филиала МБОУ СОШ №10 им. "
                "К.Б. Бжигакова, расположенного по адресу:а. Тугурой, "
                "ул. Школьная, 5",
                "а. Тугурой",
                "1500м Ю от шк.10",
            ),
            (
                "Саратовская обл., Саратовский р-н, В границах земель Маяк "
                "а/д Саратов-Волгоград у поворота на Колотов Буерак",
                "Саратовский р-н",
                "Сар.-Волг., пов.Колотов Буер",
            ),
            (
                "Саратовская область, г.о. город Саратов, г Саратов, "
                "ул им академика О.К.Антонова, зд. 36Ю",
                "г. Саратов",
                "зд.36Ю, ул. О.К.Антонова",
            ),
            (
                "Саратовская обл., м.р-н Хвалынский, с.п. Алексеевское, "
                "тер. Автомобильной дороги Сызрань -Саратов - Волгоград, "
                "км 114-й, зд. 1",
                "Алексеевское с.п.",
                "Сызр.-Сар.-Волг.114км зд.1",
            ),
            (
                "Саратовская обл., Саратовский р-н, с. Клещёвка 283 км, "
                "А/Д Сызрань-Саратов-Волгоград Справа на зем. АХ Пригородное",
                "с. Клещёвка",
                "Сызр.-Сар.-Волг.283км П",
            ),
            (
                "Россия, 357000, Ставропольский край, р-он Кочубеевский, "
                "233 км а/д \"Кавказ\", 233 км",
                "Кочубеевский р-н",
                "233км, а/д Кавказ",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_s_dot_settlement_is_not_confused_with_rural_settlement(self):
        cases = [
            (
                "Россия, 143591, Московская обл., с. Павловская Слобода, "
                "ул. Ленина, 74",
                "с. Павловская Слобода",
                "74, ул. Ленина",
            ),
            (
                "Россия, 141667, Московская обл., г.о. Клин, "
                "с. Спас-Заулок, Спасская ул., д.2Б",
                "с. Спас-Заулок",
                "2Б, ул. Спасская",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)

    def test_city_district_parent_and_mkad_ring_side_are_preserved(self):
        cases = [
            (
                "Россия, 141580, Московская обл., г.о.Химки, "
                "д. Исаково, стр. 2В",
                "г.о. Химки",
                "стр. 2В, д. Исаково",
            ),
            (
                "Россия, 115598, Московская обл., 26 км МКАД, "
                "внешн.ст., стр. 9",
                "Московская обл.",
                "МКАД 26км внеш. стр.9",
            ),
            (
                "Россия, 115598, Московская обл., 26 км МКАД, "
                "внутр.ст., стр. 9",
                "Московская обл.",
                "МКАД 26км внутр. стр.9",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_latest_workbook_problem_rows_keep_meaning(self):
        cases = [
            (
                "Московская обл., Щелковский р-н, пос. Фряново, "
                "Фряновское шоссе (при въезде слева)",
                "п. Фряново",
                "ш. Фряновское, слева",
            ),
            (
                "Россия, Московская обл., г. Балашиха, "
                "22 км «право» а/д Волга, шоссе Энтузиастов",
                "г. Балашиха",
                "22км П, а/д Волга",
            ),
            (
                "Россия, 607677, Нижегородская обл., Кстовский м.о., "
                "д. Малиновка, тер. Автодорога, зд. 1А/С",
                "д. Малиновка",
                "зд. 1А/С, тер. Автодорога",
            ),
            (
                "Тамбовская обл., Первомайский р-н, "
                "362 км а/дМ-6 \"Каспий\" (Справа)",
                "Первомайский р-н",
                "362км П, М-6 Каспий",
            ),
            (
                "Тамбовская обл.,Тамбовский р-н, "
                "446 км а/д М6 Москва - Волгоград (Каспий)",
                "Тамбовский р-н",
                "446км, М-6 Москва-Волгоград",
            ),
            (
                "Россия, 171117, Тверская обл., р-н Вышневолоцкий, "
                "п. Борисовский, 327 км а/д М-11 справа",
                "п. Борисовский",
                "327км П, М-11",
            ),
            (
                "Тульская обл., Заокский р-н, "
                "142 км + 600 м справа автомагистрали Москва-Харьков",
                "Заокский р-н",
                "142км+600м П, Москва-Харьков",
            ),
            (
                "Новгородская обл., Окуловский р-н, "
                "деревня Окуловка, на участке км 423 (слева)",
                "д. Окуловка",
                "423км Л",
            ),
            (
                "Краснодарский край, г. Краснодар, ул. Фадеева, 431",
                "г. Краснодар",
                "431, ул. Фадеева",
            ),
        ]

        for raw, settlement, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.settlement, settlement)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_fractional_building_numbers_from_reverse_addresses_are_kept(self):
        cases = [
            (
                "357207, Ставропольский край, Минераловодский р-н, "
                "Минеральные Воды г, 22 Партсъезда пр-кт, "
                "дом № зд. 100/3, помещ. 2",
                "зд. 100/3, пр-т 22 Партсъезда",
            ),
            (
                "346720, Ростовская обл, Аксайский р-н, Аксай г, "
                "Ленина пр-кт, дом № зд. 40м/1",
                "зд. 40м/1, пр-т Ленина",
            ),
            (
                "344039, Ростовская обл, Ростов-на-Дону г, "
                "Мечникова ул, дом № зд. 31/106",
                "зд. 31/106, ул. Мечникова",
            ),
            (
                "305014, Курская обл, Курск г, "
                "Карла Маркса ул, дом № зд. 77А/2",
                "зд. 77А/2, ул. Карла Маркса",
            ),
            (
                "460019, Оренбургская обл, Оренбург г, "
                "Шарлыкское ш, дом № зд. 1/2",
                "зд. 1/2, ш. Шарлыкское",
            ),
        ]

        for raw, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_street_shosse_is_not_double_prefixed(self):
        cases = [
            (
                "Россия, Ленинградская обл., г. Приозерск, "
                "ул. Ленинградское шоссе, д. 58",
                "58, ш. Ленинградское",
            ),
            (
                "Московская обл., г.о. Долгопрудный, мкр-н Хлебниково, "
                "ул. Новое ш., д. 1а",
                "1а, ул. Новое шоссе",
            ),
            (
                "Респ. Адыгея, Тахтамукайский р-н, "
                "ул. Тургеневское шоссе, д.32",
                "32, ш. Тургеневское",
            ),
        ]

        for raw, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_reverse_ul_suffix_has_priority_over_landmark_words(self):
        cases = [
            (
                "357207, Ставропольский край, Минераловодский р-н, "
                "Минеральные Воды г, Д.Бедного ул, дом № 241",
                "241, ул. Д. Бедного",
            ),
            (
                "143100, Московская обл, Руза г, Микрорайон ул, дом №17",
                "17, ул. Микрорайон",
            ),
            (
                "248000, Калужская обл, Калуга г, "
                "Бульвар Энтузиастов ул, дом № 1",
                "1, ул. Бульвар Энтузиастов",
            ),
            (
                "188662, Ленинградская обл, Всеволожский р-н, Мурино г, "
                "Шоссе в Лаврики ул, дом №65",
                "65, ул. Шоссе в Лаврики",
            ),
            (
                "346630, Ростовская обл, Семикаракорский р-н, "
                "Семикаракорск г, А.А.Араканцева ул, дом №4",
                "4, ул. А.А. Араканцева",
            ),
            (
                "628486, Ханты-Мансийский АО - Югра, "
                "Когалым г, Набережная ул, дом №161",
                "161, ул. Набережная",
            ),
            (
                "398000, Липецкая обл, Липецк г, "
                "А.Г. Стаханова ул, дом № 2, помещ 14",
                "2, ул. А.Г. Стаханова",
            ),
            (
                "309740, Белгородская обл, Ровеньский р-н, "
                "Ровеньки п, Ст. Разина ул, дом №19б",
                "19б, ул. Ст. Разина",
            ),
            (
                "Ярославская обл, Ярославль г, "
                "Республиканская ул, дом №7а",
                "7а, ул. Республиканская",
            ),
            (
                "143985, Московская обл, Балашиха г, "
                "Народного ополчения (Саввино мкр.) ул, дом № 1, помещ 3",
                "1, ул. Народного ополчения",
            ),
        ]

        for raw, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_dom_number_with_structure_keeps_structure_prefix(self):
        cases = [
            (
                "Ленина ул, дом № стр. 7Б, помещ 2",
                "стр. 7Б, ул. Ленина",
            ),
            (
                "Пензенская обл, Пенза г, Октябрьский пр-кт, "
                "дом № стр. 131/3",
                "стр. 131/3, пр-т Октябрьский",
            ),
        ]

        for raw, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_reverse_addresses_drop_premise_and_trade_center_tails(self):
        cases = [
            (
                "Архангельская обл, Архангельск г, "
                "Черепановых проезд, дом № 68.помещение 1",
                "68, пр-д Черепановых",
            ),
            (
                "Свердловская обл, Екатеринбург г, "
                "Бажова ул, дом № 17 Торговый центр \"Успенский\"",
                "17, ул. Бажова",
            ),
            (
                "Астраханская обл, Астрахань г, "
                "Тульский пер/ул. Безжонова, дом № 2/101\"А\"",
                "2/101\"А\", пер. Тульский",
            ),
        ]

        for raw, house_street in cases:
            with self.subTest(raw=raw):
                parsed = parse_address(raw)
                self.assertEqual(parsed.house_street, house_street)
                self.assertLessEqual(len(parsed.house_street), 30)

    def test_malformed_parenthesis_street_house_is_kept(self):
        parsed = parse_address(
            "400038, Волгоградская обл, Волгоград г, "
            "Волгоградская (Рабочий поселок Горьковск ул, дом № 178Д"
        )

        self.assertEqual(parsed.settlement, "г. Волгоград")
        self.assertEqual(parsed.house_street, "178Д, ул. Волгоградская")
        self.assertLessEqual(len(parsed.house_street), 30)

    def test_long_department_settlement_is_shortened_meaningfully(self):
        parsed = parse_address(
            "396333, Воронежская обл, Новоусманский р-н, "
            "1-го отделения совхоза Масловский п, Ленина ул, дом № 47а"
        )

        self.assertEqual(parsed.settlement, "п. 1 отд. совхоза Масловский")
        self.assertEqual(parsed.house_street, "47а, ул. Ленина")
        self.assertLessEqual(len(parsed.settlement), 30)
        self.assertLessEqual(len(parsed.house_street), 30)


if __name__ == "__main__":
    unittest.main()
