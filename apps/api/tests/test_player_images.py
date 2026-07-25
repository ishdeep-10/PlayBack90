from app.services import player_images


def test_resolve_player_image_matches_short_unique_name_from_provider_full_name(monkeypatch):
    monkeypatch.setattr(
        player_images,
        "_load_index",
        lambda: (
            {
                "cristiano ronaldo": "https://example.test/ronaldo.png",
                "santos cristiano": "https://example.test/wrong-santos.png",
                "ronaldo vieira": "https://example.test/vieira.png",
            },
            {},
            {},
        ),
    )

    assert (
        player_images.resolve_player_image("Cristiano Ronaldo dos Santos Aveiro")
        == "https://example.test/ronaldo.png"
    )


def test_resolve_player_image_rejects_ambiguous_partial_name(monkeypatch):
    monkeypatch.setattr(
        player_images,
        "_load_index",
        lambda: (
            {
                "jordan henderson": "https://example.test/henderson-1.png",
                "brian henderson": "https://example.test/henderson-2.png",
            },
            {},
            {},
        ),
    )

    assert player_images.resolve_player_image("Jordan Brian Henderson") is None
