import pytest

from webdriver.bidi.modules.script import ContextTarget
from ... import recursive_compare


@pytest.mark.asyncio
async def test_arguments(bidi_session, top_context):
    result = await bidi_session.script.call_function(
        function_declaration="(...args)=>{return args}",
        arguments=[{
            "type": "string",
            "value": "ARGUMENT_STRING_VALUE"
        }, {
            "type": "number",
            "value": 42}],
        await_promise=False,
        target=ContextTarget(top_context["context"]))

    recursive_compare({
        "type": "array",
        "value": [{
            "type": 'string',
            "value": 'ARGUMENT_STRING_VALUE'
        }, {
            "type": 'number',
            "value": 42}]},
        result)


@pytest.mark.asyncio
async def test_default_arguments(bidi_session, top_context):
    result = await bidi_session.script.call_function(
        function_declaration="(...args)=>{return args}",
        await_promise=False,
        target=ContextTarget(top_context["context"]))

    recursive_compare({
        "type": "array",
        "value": []
    }, result)


@pytest.mark.asyncio
async def test_remote_value_argument(bidi_session, top_context):
    remote_value_result = await bidi_session.script.evaluate(
        expression="({SOME_PROPERTY:'SOME_VALUE'})",
        await_promise=False,
        result_ownership="root",
        target=ContextTarget(top_context["context"]))

    remote_value_handle = remote_value_result["handle"]

    result = await bidi_session.script.call_function(
        function_declaration="(obj)=>{return obj.SOME_PROPERTY;}",
        arguments=[{
            "handle": remote_value_handle}],
        await_promise=False,
        target=ContextTarget(top_context["context"]))

    assert result == {
        "type": "string",
        "value": "SOME_VALUE"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "argument, expected",
    [
        ({"type": "undefined"}, "undefined"),
        ({"type": "null"}, "null"),
        ({"type": "string", "value": "foobar"}, "'foobar'"),
        ({"type": "string", "value": "2"}, "'2'"),
        ({"type": "number", "value": "-0"}, "-0"),
        ({"type": "number", "value": "Infinity"}, "Infinity"),
        ({"type": "number", "value": "-Infinity"}, "-Infinity"),
        ({"type": "number", "value": 3}, "3"),
        ({"type": "number", "value": 1.4}, "1.4"),
        ({"type": "boolean", "value": True}, "true"),
        ({"type": "boolean", "value": False}, "false"),
        ({"type": "bigint", "value": "42"}, "42n"),
    ],
)
async def test_primitive_values(bidi_session, top_context, argument, expected):
    result = await bidi_session.script.call_function(
        function_declaration=
        f"""(arg) => {{
            if(arg!=={expected})
                throw Error("Argument should be {expected}, but was "+arg);
            return arg;
        }}""",
        arguments=[argument],
        await_promise=False,
        target=ContextTarget(top_context["context"]),
    )

    recursive_compare(argument, result)


@pytest.mark.asyncio
async def test_nan(bidi_session, top_context):
    nan_remote_value = {"type": "number", "value": "NaN"}
    result = await bidi_session.script.call_function(
        function_declaration=
        f"""(arg) => {{
            if(!isNaN(arg))
                throw Error("Argument should be 'NaN', but was "+arg);
            return arg;
        }}""",
        arguments=[nan_remote_value],
        await_promise=False,
        target=ContextTarget(top_context["context"]),
    )

    recursive_compare(nan_remote_value, result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "argument, expected_type",
    [
        ({
             "type": "array",
             "value": [
                 {"type": "string", "value": "foobar"},
             ],
         },
         "Array"
        ),
        ({"type": "date", "value": "2022-05-31T13:47:29.000Z"},
         "Date"
         ),
        ({
             "type": "map",
             "value": [
                 ["foobar", {"type": "string", "value": "foobar"}],
             ],
         },
         "Map"
        ),
        ({
             "type": "object",
             "value": [
                 ["foobar", {"type": "string", "value": "foobar"}],
             ],
         },
         "Object"
        ),
        ({"type": "regexp", "value": {"pattern": "foo", "flags": "g"}},
         "RegExp"
         ),
        ({
             "type": "set",
             "value": [
                 {"type": "string", "value": "foobar"},
             ],
         },
         "Set"
        )
    ],
)
async def test_local_values(bidi_session, top_context, argument, expected_type):
    result = await bidi_session.script.call_function(
        function_declaration=
        f"""(arg) => {{
            if(! (arg instanceof {expected_type}))
                throw Error("Argument type should be {expected_type}, but was "+
                    Object.prototype.toString.call(arg));
            return arg;
        }}""",
        arguments=[argument],
        await_promise=False,
        target=ContextTarget(top_context["context"]),
    )

    recursive_compare(argument, result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value_fn, function_declaration",
    [
        (
            lambda value: value,
            "function(arg) { return arg === window.SOME_OBJECT; }",
        ),
        (
            lambda value: ({"type": "object", "value": [["nested", value]]}),
            "function(arg) { return arg.nested === window.SOME_OBJECT; }",
        ),
        (
            lambda value: ({"type": "array", "value": [value]}),
            "function(arg) { return arg[0] === window.SOME_OBJECT; }",
        ),
        (
            lambda value: ({"type": "map", "value": [["foobar", value]]}),
            "function(arg) { return arg.get('foobar') === window.SOME_OBJECT; }",
        ),
        (
            lambda value: ({"type": "set", "value": [value]}),
            "function(arg) { return arg.has(window.SOME_OBJECT); }",
        ),
    ],
)
async def test_remote_value_deserialization(
    bidi_session, top_context, call_function, evaluate, value_fn, function_declaration
):
    remote_value = await evaluate(
        "window.SOME_OBJECT = {SOME_PROPERTY:'SOME_VALUE'}; window.SOME_OBJECT",
        result_ownership="root",
    )

    # Check that a remote value can be successfully deserialized as an "argument"
    # parameter and compared against the original object in the page.
    result = await call_function(
        function_declaration=function_declaration,
        arguments=[value_fn(remote_value)],
    )
    assert result == {"type": "boolean", "value": True}

    # Reload the page to cleanup the state
    await bidi_session.browsing_context.navigate(
        context=top_context["context"], url=top_context["url"], wait="complete"
    )
