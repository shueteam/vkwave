from vkwave.api.token.token import Token, BotSyncSingleToken
from vkwave.bots.utils.uploaders.photo_uploader import PhotoUploader
from vkwave.client.default import AIOHTTPClient
from vkwave.api.methods import API
import asyncio

client = AIOHTTPClient()
api = API(
    clients=client,
    tokens=BotSyncSingleToken(
        Token(
            "token"
        )
    ),
)

uploader = PhotoUploader(api.get_context())


async def main():
    big_attachment = await uploader.get_attachments_from_links(
        peer_id=1234,
        links=[
            "https://user-images.githubusercontent.com/28061158/75329873-7f738200-5891-11ea-9565-fd117ea4fc9e.jpg",
            "https://camo.githubusercontent.com/9c8d6519e5997860b7a4b28f74719c0c2f83142b/68747470733a2f2f692e696d6775722e636f6d2f386955334578366c2e6a7067",
            "https://user-images.githubusercontent.com/28061158/74590410-239e3300-501f-11ea-9774-27ee507a1e1e.jpg",
        ],
    )
    await api.get_context().messages.send(
        user_id=1234, attachment=big_attachment, random_id=0
    )
    # TODO: voice


asyncio.get_event_loop().run_until_complete(main())
