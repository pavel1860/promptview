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
        if history.turn.local_state is not None:
            self.store: Dict[str, Any] = history.turn.local_state.get(self._prompt_name, {})
        else:
            self.store: Dict[str, Any] = {}
        
    def get(self, key: str) -> Any:
        return self.store.get(key)
    
    def set(self, key: str, value: Any):
        self.store[key] = value
        if not self._prompt_name:
            raise ValueError("Prompt name is required to update local state")
        self._history.update_turn_local_state(self._prompt_name, self.store)
    
    

    
    
class LocalState(Generic[T]):
    """Descriptor-based state container"""
    def __init__(self, store: LocalStore, key: str, initial: T):
        self._store = store
        self._key = key
        self._model_class = initial.__class__ if isinstance(initial, BaseModel) else None
        self._value: T = initial
        
        # Initialize store
        if isinstance(initial, BaseModel):
            self._store.set(key, initial.model_dump())
        else:
            self._store.set(key, initial)
    
    @property
    def value(self) -> T:
        return self._value
    
    @property
    def is_model(self) -> bool:
        return self._model_class is not None
    
    def update(self):
        current = self._store.get(self._key)
        if current is not None:
            if self._model_class:
                self._value = self._model_class(**current)
            else:
                self._value = current

    def get(self) -> T:
        current = self._store.get(self._key)
        if self._model_class:
            return self._model_class(**current)
        return current
    
    def set(self, value: T):
        if isinstance(value, BaseModel):
            self._store.set(self._key, value.model_dump())
        else:
            self._store.set(self._key, value)
        self._value = value
        
    


class TurnHooks:
    def __init__(self, history: History, prompt_name: str | None = None):        
        self._prompt_name = prompt_name
        self._local_store: LocalStore = LocalStore(history, prompt_name)

    def use_var(self, key: str, initial: StateType) -> LocalState[StateType]:
        state = LocalState(self._local_store, key, initial)
        state.set(initial)        
        return state
    
    def use_state(self, key: str, initial: StateType) -> Tuple[LocalState[StateType], Callable[[StateType, bool], None]]:
        state = LocalState(self._local_store, key, initial)
        state.set(initial)
        
        def set_state(value: StateType, merge: bool = False):
            if merge:
                if state.is_model:
                    state.set(state.value.model_copy(update=value.model_dump()))
                elif isinstance(state.value, dict):
                    new_value = state.value | value
                    state.set(new_value)
                else:
                    state.set(value)
            else:
                state.set(value)
        
        return state, set_state
        
    