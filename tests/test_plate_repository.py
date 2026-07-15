import inspect

from app.repositories.plates import PlateRepository


def test_create_state_sale_casts_nullable_reservation_user_id_to_bigint() -> None:
    source = inspect.getsource(PlateRepository.create_state_sale)

    assert "$3::bigint" in source
