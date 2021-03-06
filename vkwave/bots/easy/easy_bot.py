import asyncio
import typing
import inspect

from vkwave.api.methods import API
from vkwave.api.token.token import BotSyncPoolTokens, BotSyncSingleToken, Token
from vkwave.bots.core import BaseFilter
from vkwave.bots.core.dispatching.dp.dp import Dispatcher
from vkwave.bots.core.dispatching.events.base import BaseEvent, BotEvent
from vkwave.bots.core.dispatching.extensions.longpoll_bot import BotLongpollExtension
from vkwave.bots.core.dispatching.filters.builtin import (
    ChatActionFilter,
    CommandsFilter,
    EventTypeFilter,
    PayloadFilter,
    RegexFilter,
    TextFilter,
)
from vkwave.bots.fsm.filters import StateFilter
from vkwave.bots.core.dispatching.handler.callback import BaseCallback
from vkwave.bots.core.dispatching.router.router import DefaultRouter
from vkwave.bots.core.tokens.storage import TokenStorage
from vkwave.bots.core.tokens.types import GroupId
from vkwave.client.default import AIOHTTPClient
from vkwave.longpoll.bot import BotLongpoll, BotLongpollData
from vkwave.types.bot_events import BotEventType
from vkwave.types.objects import BaseBoolInt


class _APIContextManager:
    def __init__(self, tokens: typing.Union[str, typing.List[str]]):
        self.client = AIOHTTPClient()
        self.tokens = (
            BotSyncSingleToken(Token(tokens))
            if isinstance(tokens, str)
            else BotSyncPoolTokens([Token(token) for token in tokens])
        )
        self.api = API(clients=self.client, tokens=self.tokens)

    async def __aenter__(self):
        return self.api.get_context()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        await self.client.close()


def create_api_session_aiohttp(token: str) -> _APIContextManager:
    return _APIContextManager(token)


class SimpleBotEvent(BotEvent):
    def __init__(self, event: BotEvent):
        super().__init__(event.object, event.api_ctx)

    async def answer(
        self,
        message: typing.Optional[str] = None,
        keyboard: typing.Optional[str] = None,
        attachment: typing.Optional[BaseBoolInt] = None,
        payload: typing.Optional[str] = None,
        forward_messages: typing.Optional[typing.List[int]] = None,
        dont_parse_links: typing.Optional[bool] = None,
        disable_mentions: typing.Optional[bool] = None,
        sticker_id: typing.Optional[int] = None,
        domain: typing.Optional[str] = None,
        lat: typing.Optional[BaseBoolInt] = None,
        long: typing.Optional[BaseBoolInt] = None,
        reply_to: typing.Optional[int] = None,
        group_id: typing.Optional[int] = None,
    ):
        await self.api_ctx.messages.send(
            domain=domain,
            lat=lat,
            long=long,
            attachment=attachment,
            reply_to=reply_to,
            forward_messages=forward_messages,
            sticker_id=sticker_id,
            group_id=group_id,
            keyboard=keyboard,
            payload=payload,
            dont_parse_links=dont_parse_links,
            disable_mentions=disable_mentions,
            peer_id=self.object.object.message.peer_id,
            message=message,
            random_id=0,
        )


class SimpleLongPollBot:
    def __init__(
        self, tokens: typing.Union[str, typing.List[str]], group_id: int,
    ):
        self.SimpleBotEvent = SimpleBotEvent
        self.api_session = create_api_session_aiohttp(tokens)
        self.api_context = self.api_session.api.get_context()
        self._lp = BotLongpoll(self.api_context, BotLongpollData(group_id))
        self._token_storage = TokenStorage[GroupId]()
        self.dispatcher = Dispatcher(self.api_session.api, self._token_storage)
        self._lp = BotLongpollExtension(self.dispatcher, self._lp)
        self.router = DefaultRouter()
        self.handler = self.router.registrar.with_decorator
        self.dispatcher.add_router(self.router)

        self.text_filter = TextFilter
        self.event_type_filter = EventTypeFilter
        self.payload_filter = PayloadFilter
        self.chat_action_filter = ChatActionFilter
        self.command_filter = CommandsFilter
        self.regex_filter = RegexFilter
        self.state_filter = StateFilter

    class SimpleBotCallback(BaseCallback):
        def __init__(self, func: typing.Callable[[BaseEvent], typing.Awaitable[typing.Any]]):
            self.func = func

        async def execute(self, event: BotEvent) -> typing.Any:
            new_event = SimpleBotEvent(event)
            if inspect.iscoroutinefunction(self.func):
                return await self.func(new_event)
            return self.func(new_event)

    def message_handler(self, *filters: BaseFilter):
        def decorator(func: typing.Callable[..., typing.Any]):
            record = self.router.registrar.new()
            record.with_filters(*filters)
            record.filters.append(EventTypeFilter(BotEventType.MESSAGE_NEW))
            record.handle(self.SimpleBotCallback(func))
            handler = record.ready()
            self.router.registrar.register(handler)
            return func

        return decorator

    async def run(self):
        await self.dispatcher.cache_potential_tokens()
        await self._lp.start()

    def run_forever(self, loop: typing.Optional[asyncio.AbstractEventLoop] = None):
        loop = loop or asyncio.get_event_loop()
        loop.create_task(self.run())
        loop.run_forever()


class ClonesBot:
    """
    Create many bots with the same functionality
    """

    def __init__(self, base_bot: SimpleLongPollBot, *clones: SimpleLongPollBot):
        self.base_bot = base_bot
        self.router = self.base_bot.router
        self.clones: typing.Tuple[SimpleLongPollBot] = clones

    def run_all_bots(self, loop: typing.Optional[asyncio.AbstractEventLoop] = None):
        loop = loop or asyncio.get_event_loop()
        loop.create_task(self.base_bot.run())
        for clone in self.clones:
            clone.router.registrar.handlers.extend(self.router.registrar.handlers)
            clone.router.registrar.handlers = list(set(clone.router.registrar.handlers))
            loop.create_task(clone.run())
        loop.run_forever()
