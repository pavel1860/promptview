from typing import Type, TypeVar, Generic, Any, Dict, TypeVar, Union, Callable, Tuple
from pydantic import BaseModel

from ..conversation.history import History
from ..conversation.models import Turn

StateType = TypeVar('StateType', bound=Union[Any, BaseModel])


T = TypeVar('T')


    
class LocalStore():
    
    
    def __init__(self, history: History, prompt_name: str | None = None):
        self._history = history
        self.turn = history.turn        
        self._prompt_name = prompt_name
        if history.turn and history.turn.localState is not None:
            local_state = history.turn.localState 
            self.store: Dict[str, Any] = local_state.get(self._prompt_name, {})
        else:
            self.store: Dict[str, Any] = {}
        
    def get(self, key: str) -> Any:
        return self.store.get(key)
    
    async def set(self, key: str, value: Any):
        self.store[key] = value
        if not self._prompt_name:
            raise ValueError("Prompt name is required to update local state")
        await self._history.update_turn_local_state(self._prompt_name, self.store)
    
    

    
    
class LocalState(Generic[StateType]):
    """Descriptor-based state container"""
    def __init__(self, store: LocalStore, key: str, initial: StateType):
        self._store = store
        self._key = key
        self._initial = initial
        self.is_model = isinstance(initial, BaseModel)
        
    def get(self) -> StateType:
        value = self._store.get(self._key)
        if value is None:
            return self._initial
        if self.is_model:
            if isinstance(value, dict):
                return self._initial.__class__(**value)
            return value
        return value
    
    @property
    def value(self) -> StateType:
        return self.get()
    
    async def set(self, value: StateType):
        if self.is_model:
            await self._store.set(self._key, value.model_dump())
        else:
            await self._store.set(self._key, value)


class TurnHooks:
    def __init__(self, history: History, prompt_name: str | None = None):        
        self._prompt_name = prompt_name
        self._local_store: LocalStore = LocalStore(history, prompt_name)

    async def use_var(self, key: str, initial: StateType) -> LocalState[StateType]:
        state = LocalState(self._local_store, key, initial)
        await state.set(initial)        
        return state
    
    async def use_state(self, key: str, initial: StateType) -> Tuple[LocalState[StateType], Callable[[StateType, bool], None]]:
        state = LocalState(self._local_store, key, initial)
        await state.set(initial)
        
        async def set_state(value: StateType, merge: bool = False):
            if merge:
                if state.is_model:
                    await state.set(state.value.model_copy(update=value.model_dump()))
                elif isinstance(state.value, dict):
                    new_value = state.value | value
                    await state.set(new_value)
                else:
                    await state.set(value)
            else:
                await state.set(value)
        
        return state, set_state
        
    