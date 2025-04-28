

import contextvars
from typing import Any
from promptview.tracer.langsmith_tracer import RunTypes
from ..tracer import Tracer


CURR_CONTEXT = contextvars.ContextVar("curr_context")



class ExecutionContext:
    
    
    def __init__(self, span_name: str | None = None):
        self._tracer_run = None
        self._trace_id = None
        self._parent_ctx = None
        self._span_name = span_name
    
    @property
    def trace_id(self):  
        if self._tracer_run is not None:      
            return str(self._tracer_run.id)
        return self._trace_id

    @trace_id.setter
    def trace_id(self, value: str):
        self._trace_id = value
    
    @property
    def tracer(self):
        if self._tracer_run is None:
            raise ValueError("Tracer not set")
        return self._tracer_run
    
    @classmethod
    def get_current(cls, raise_error: bool = True):
        try:            
            ctx = CURR_CONTEXT.get()
        except LookupError:
            if raise_error:
                raise ValueError("Context not set")
            else:
                return None        
        if not issubclass(ctx, ExecutionContext):
            if raise_error:
                raise ValueError("Context is not a Context")
            else:
                return None
        return ctx
    
    def _set_context(self):
        self._ctx_token = CURR_CONTEXT.set(self)
        
        
    def _reset_context(self):
        if self._ctx_token is not None:
            CURR_CONTEXT.reset(self._ctx_token)
        self._ctx_token = None

    def build_child(self, span_name: str | None = None):
        child = ExecutionContext(span_name=span_name)
        child._parent_ctx = self
        return child
        
    def start_tracer(self, name: str, run_type: RunTypes = "prompt", inputs: dict[str, Any] | None = None):
        self._tracer_run = Tracer(
            name=name,
            run_type=run_type,
            inputs=inputs,
            is_traceable=True,
            tracer_run=self._parent_ctx._tracer_run if self._parent_ctx is not None else None,
        )
        return self
    
    
    async def __aenter__(self):    
        # if self._branch is None or self._turn is None:
            # raise ValueError("Branch or turn not set")
        self._set_context()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        self._reset_context()
        if self._tracer_run is not None:
            self._tracer_run.__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            return False        
        return True
