import databases


def test_save_and_get_channel_media_map():
    channel_id = 100
    media_ids = [1, 2, 3]
    databases.save_channel_media_map(channel_id, media_ids)
    assert databases.get_channel_media_map(channel_id) == media_ids


def test_is_channel_in_mappings():
    channel_id = 200
    assert databases.is_channel_in_mappings(channel_id) is False
    databases.save_channel_media_map(channel_id, [5])
    assert databases.is_channel_in_mappings(channel_id) is True


def test_link_user_to_channel_upserts():
    user_id = 123
    databases.link_user_to_channel(user_id, 1)
    assert databases.get_user_channel(user_id) == 1
    databases.link_user_to_channel(user_id, 2)
    assert databases.get_user_channel(user_id) == 2


def test_get_channel_users_returns_all():
    channel_id = 999
    databases.link_user_to_channel(1, channel_id)
    databases.link_user_to_channel(2, channel_id)
    databases.link_user_to_channel(3, 42)
    assert sorted(databases.get_channel_users(channel_id)) == [1, 2]
