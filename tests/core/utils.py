from brickworks.core.models.user_model import UserModel


async def create_test_user(user_given_name: str, user_family_name: str) -> UserModel:
    """
    Create a test user with the given name and family name.
    """
    test_user = await UserModel(
        sub=user_given_name.lower(),
        name=f"{user_given_name} {user_family_name}",
        given_name=user_given_name,
        family_name=user_family_name,
        email=f"{user_given_name}@example.com",
    ).persist()
    return test_user
