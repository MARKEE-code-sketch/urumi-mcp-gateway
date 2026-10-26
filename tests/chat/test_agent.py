import asyncio
import copy
import json
from datetime import datetime, timezone

import pytest

from backend.chat.agent import ChatAgent, compatible_schema, result_text
from backend.chat.day_window import DayWindow
from backend.chat.llm_client import ChatFailure, encoded
from backend.chat.search_results import SEARCH_BUDGET
from backend.errors import PlatformError
from scripts.m7.fixtures import GatewayFixture, IdentityFixture, ScriptedProvider, result, tool_call

NOW = datetime(2026, 10, 18, 6, 30, tzinfo=timezone.utc)
ANSWER = {'role': 'assistant', 'content': 'Observed fixture answer.'}


def setup(replies, handler=None, **kwargs):
    identity = IdentityFixture()
    gateway = GatewayFixture(identity, handler)
    provider = ScriptedProvider(replies)
    agent = ChatAgent(provider, gateway, identity, clock=lambda: NOW, **kwargs)
    return agent, provider, gateway, identity


def test_real_principal_proof_and_identity_attribution():
    agent, provider, gateway, identity = setup([tool_call(), ANSWER, tool_call(), ANSWER])
    first = asyncio.run(agent.run(identity.a, 'sample stock'))
    second = asyncio.run(agent.run(identity.b, 'sample stock'))
    assert first['state'] == second['state'] == 'completed'
    assert gateway.calls[0][0] is identity.a and gateway.calls[1][0] is identity.b
    assert first['tool_calls'][0]['audit_id'] != second['tool_calls'][0]['audit_id']
    assert gateway.list_count == 2
    with pytest.raises(PlatformError):
        asyncio.run(agent.run({'user_id': str(identity.a.user_id)}, 'spoof'))


def test_create_product_exact_name_price_once_and_pairing():
    args = {'name': 'Blue Mug', 'regular_price': '299.00'}
    agent, provider, gateway, identity = setup([tool_call('woocommerce__create_product', args, 'create-1'), ANSWER])
    reply = asyncio.run(agent.run(identity.a, 'create Blue Mug for INR299'))
    assert reply['state'] == 'completed' and len(gateway.calls) == 1 and gateway.calls[0][2] == args
    assert provider.requests[1][0][-1]['tool_call_id'] == 'create-1'
    assert reply['tool_calls'][0]['call_id'] != 'create-1'


def test_cross_server_uses_observed_sku_and_current_user():
    agent, provider, gateway, identity = setup([
        tool_call('woocommerce__list_products', {'sku': 'DEMO-001'}, 'product'),
        tool_call(call_id='inventory'), ANSWER])
    reply = asyncio.run(agent.run(identity.b, 'find product then sample warehouse'))
    assert reply['state'] == 'completed'
    assert [call[1] for call in gateway.calls] == ['woocommerce__list_products', 'inventory__lookup_sku']
    assert all(call[0] is identity.b for call in gateway.calls)
    assert 'DEMO-001' in provider.requests[1][0][-1]['content']


@pytest.mark.parametrize('mutation', ['unknown', 'id', 'array', 'invalid', 'oversized', 'batch'])
def test_invalid_model_calls_dispatch_nothing(mutation):
    call = tool_call()
    if mutation == 'unknown': call['tool_calls'][0]['function']['name'] = 'other__tool'
    if mutation == 'id': call['tool_calls'][0]['id'] = ''
    if mutation == 'array': call['tool_calls'][0]['function']['arguments'] = '[]'
    if mutation == 'invalid': call['tool_calls'][0]['function']['arguments'] = '{'
    if mutation == 'oversized': call['tool_calls'][0]['function']['arguments'] = 'x' * 8193
    if mutation == 'batch': call['tool_calls'] *= 2
    agent, _, gateway, identity = setup([call])
    assert asyncio.run(agent.run(identity.a, 'question'))['state'] == 'failed'
    assert gateway.calls == []


@pytest.mark.parametrize('kind', ['duplicate_id', 'write_replay'])
def test_replayed_ids_and_reordered_writes_do_not_dispatch_twice(kind):
    name, args = 'woocommerce__create_product', {'name': 'Mug', 'regular_price': '1.00'}
    second = tool_call(name, dict(reversed(list(args.items()))), 'first' if kind == 'duplicate_id' else 'second')
    agent, _, gateway, identity = setup([tool_call(name, args, 'first'), second])
    reply = asyncio.run(agent.run(identity.a, 'create mug'))
    assert reply['state'] == 'failed' and len(gateway.calls) == 1


def test_eighth_round_reserved_for_final_answer_no_ninth():
    replies = [tool_call(call_id=str(index)) for index in range(7)] + [ANSWER]
    agent, provider, gateway, identity = setup(replies)
    assert asyncio.run(agent.run(identity.a, 'stock'))['state'] == 'completed'
    assert len(provider.requests) == 8 and len(gateway.calls) == 7
    assert provider.requests[-1][2] is True
    agent, provider, gateway, identity = setup([tool_call(call_id=str(index)) for index in range(8)])
    assert asyncio.run(agent.run(identity.a, 'stock'))['state'] == 'failed'
    assert len(provider.requests) == 8 and len(gateway.calls) == 7


@pytest.mark.parametrize('outcome', ['timeout', 'unknown'])
def test_uncertain_outcome_stops_without_model_retry(outcome):
    agent, provider, gateway, identity = setup([tool_call(), ANSWER])
    gateway.outcome = outcome
    reply = asyncio.run(agent.run(identity.a, 'stock'))
    assert reply['state'] == 'failed' and len(provider.requests) == len(gateway.calls) == 1
    assert reply['tool_calls'][0]['outcome'] == outcome and 'uncertain' in reply['answer']


@pytest.mark.parametrize('code,audit,outcome', [('AUDIT_UNAVAILABLE', False, 'denied'),
    ('AUDIT_FINALIZATION_FAILED', True, 'unknown')])
def test_audit_failure_metadata_is_honest(code, audit, outcome):
    async def failure(name, args):
        raise PlatformError(503, code, 'unsafe provider error must not surface')
    agent, _, _, identity = setup([tool_call()], failure)
    reply = asyncio.run(agent.run(identity.a, 'stock'))
    call = reply['tool_calls'][0]
    assert bool(call['audit_id']) is audit and call['outcome'] == outcome and call['error_code'] == code
    assert 'unsafe provider' not in json.dumps(reply)


def today_arguments():
    window = DayWindow.capture('today', NOW)
    return {'created_from': window.start.isoformat(), 'created_to': window.end.isoformat(), 'page': 1}


def test_today_midnight_previous_utc_date_and_automatic_pages():
    args = today_arguments()
    assert args['created_from'].startswith('2026-10-17T18:30:00')
    async def pages(name, arguments):
        page = arguments['page']
        return result({'items': [{'id': page, 'date_created': args['created_from']}],
                       'page': page, 'per_page': 20, 'has_more': page < 2})
    agent, provider, gateway, identity = setup([tool_call('woocommerce__list_orders', args), ANSWER], pages)
    reply = asyncio.run(agent.run(identity.a, "today's orders"))
    assert reply['state'] == 'completed' and len(reply['tool_calls']) == 2
    assert [call[2]['page'] for call in gateway.calls] == [1, 2]
    assert gateway.calls[0][2]['created_to'] == gateway.calls[1][2]['created_to']
    assert json.loads(provider.requests[1][0][-1]['content'])['complete'] is True


@pytest.mark.parametrize('change', ['missing', 'status', 'wrong_date', 'wrong_page'])
def test_today_argument_guard_not_prompt_only(change):
    args = today_arguments()
    if change == 'missing': del args['created_to']
    if change == 'status': args['status'] = 'completed'
    if change == 'wrong_date': args['created_from'] = '2026-10-18T00:00:00Z'
    if change == 'wrong_page': args['page'] = 2
    agent, _, gateway, identity = setup([tool_call('woocommerce__list_orders', args)])
    assert asyncio.run(agent.run(identity.a, 'today orders'))['state'] == 'failed'
    assert gateway.calls == []


def test_thirteenth_auto_page_stopped_partial_no_model_false_completion():
    args = today_arguments()
    async def pages(name, arguments):
        return result({'items': [{'id': arguments['page'], 'date_created': args['created_from']}],
            'page': arguments['page'], 'per_page': 20, 'has_more': True})
    agent, provider, gateway, identity = setup([tool_call('woocommerce__list_orders', args), ANSWER], pages)
    reply = asyncio.run(agent.run(identity.a, 'today orders'))
    assert reply['state'] == 'limit_reached' and len(gateway.calls) == 12 and len(provider.requests) == 1
    assert 'partial' in reply['answer']


@pytest.mark.parametrize('mode', ['outside', 'repeat', 'bad_metadata'])
def test_invalid_order_pages_stop_partial(mode):
    args = today_arguments()
    async def pages(name, arguments):
        return result({'items': [{'id': 1, 'date_created': '2026-10-16T00:00:00Z' if mode == 'outside' else args['created_from']}],
            'page': 1 if mode == 'bad_metadata' else arguments['page'], 'per_page': 20, 'has_more': True})
    agent, _, gateway, identity = setup([tool_call('woocommerce__list_orders', args)], pages)
    reply = asyncio.run(agent.run(identity.a, 'today orders'))
    assert reply['state'] == 'failed' and 'partial' in reply['answer'] and len(gateway.calls) <= 2


def test_expiry_between_model_and_dispatch_blocks_call():
    agent, provider, gateway, identity = setup([])
    async def expire(*args):
        identity.valid.clear()
        return tool_call()
    provider.replies = [expire]
    reply = asyncio.run(agent.run(identity.a, 'stock'))
    assert reply['state'] == 'failed' and gateway.calls == []


@pytest.mark.parametrize('kind', ['image', 'large'])
def test_unsupported_large_content_never_replayed(kind):
    async def handler(name, args):
        return {'content': [{'type': 'image', 'data': 'AA=='}]} if kind == 'image' else result({'text': 'x' * 33000})
    agent, provider, gateway, identity = setup([tool_call(), ANSWER], handler)
    reply = asyncio.run(agent.run(identity.a, 'stock'))
    assert reply['state'] in ('failed', 'limit_reached') and len(gateway.calls) == 1
    assert reply['tool_calls'][0]['outcome'] == 'success' and len(provider.requests) == 1


def test_unsupported_schema_is_disclosed_and_not_offered():
    agent, provider, gateway, identity = setup([ANSWER])
    gateway.tools[0]['inputSchema'] = {'type': 'object', '$ref': 'https://metadata.test/schema'}
    reply = asyncio.run(agent.run(identity.a, 'hello'))
    assert 'cannot use' in reply['answer'] and len(provider.requests[0][1]) == 5
    assert compatible_schema({'type': 'object', '$defs': {'a': {'type': 'string'}}, 'properties': {'x': {'$ref': '#/$defs/a'}}})
    assert not compatible_schema({'type': 'object', '$ref': '#/$defs/a', '$defs': {'a': {'$ref': '#/$defs/a'}}})


def test_catalog_cap_fails_before_inference():
    agent, provider, gateway, identity = setup([ANSWER])
    gateway.tools = [dict(copy.deepcopy(gateway.tools[0]), name='tool_' + str(index)) for index in range(65)]
    reply = asyncio.run(agent.run(identity.a, 'hello'))
    assert reply['state'] == 'limit_reached' and provider.requests == [] and gateway.calls == []


def test_deadline_and_two_message_limit_release_slots():
    async def scenario():
        started = asyncio.Event()
        async def stall(*args):
            started.set()
            await asyncio.sleep(10)
        agent, provider, gateway, identity = setup([stall, stall], deadline=0.1)
        first = asyncio.create_task(agent.run(identity.a, 'one'))
        await started.wait()
        second = asyncio.create_task(agent.run(identity.b, 'two'))
        await asyncio.sleep(0.01)
        with pytest.raises(PlatformError):
            await agent.run(identity.a, 'third')
        replies = await asyncio.gather(first, second)
        assert all(reply['state'] == 'limit_reached' for reply in replies)
        assert agent.active == 0 and gateway.calls == []
    asyncio.run(scenario())


def test_provider_failure_keeps_prior_attempt_and_redacts_key():
    agent, provider, gateway, identity = setup([tool_call(), ChatFailure('PROVIDER_RATE_LIMIT', 'Model unavailable.')])
    reply = asyncio.run(agent.run(identity.a, 'stock'))
    assert reply['state'] == 'failed' and len(reply['tool_calls']) == 1
    agent, _, _, identity = setup([dict(ANSWER, content='fixture-provider-key')])
    assert asyncio.run(agent.run(identity.a, 'hello'))['answer'] == '[REDACTED]'


def test_failed_second_order_page_cannot_be_claimed_complete():
    args = today_arguments()
    agent, provider, gateway, identity = setup([tool_call('woocommerce__list_orders', args),
        dict(ANSWER, content='These are all orders today.')])
    async def pages(name, arguments):
        if arguments['page'] == 2:
            gateway.outcome = 'error'
            return {'isError': True, 'content': [{'type': 'text', 'text': 'safe tool failure'}]}
        return result({'items': [{'id': 1, 'date_created': args['created_from']}], 'page': 1,
                       'per_page': 20, 'has_more': True})
    gateway.handler = pages
    reply = asyncio.run(agent.run(identity.a, 'today orders'))
    assert reply['state'] == 'failed' and 'partial' in reply['answer']
    assert len(provider.requests) == 1 and [call['outcome'] for call in reply['tool_calls']] == ['success', 'error']


def test_successful_write_with_unsupported_reply_is_not_reported_failed_write():
    async def image(name, arguments):
        return {'content': [{'type': 'image', 'data': 'AA=='}], 'isError': False}
    agent, provider, gateway, identity = setup([tool_call('woocommerce__create_product',
        {'name': 'Mug', 'regular_price': '1.00'}), ANSWER], image)
    reply = asyncio.run(agent.run(identity.a, 'create mug'))
    assert reply['tool_calls'][0]['outcome'] == 'success' and 'gateway reported success' in reply['answer']
    assert 'Do not repeat' in reply['answer'] and len(gateway.calls) == 1


def test_canceled_blocking_threads_keep_capacity_until_real_exit():
    import threading
    async def scenario():
        agent, _, _, _ = setup([])
        entered, release = threading.Event(), threading.Event()
        def blocking():
            entered.set()
            release.wait(2)
        first = asyncio.create_task(agent.blocking(blocking))
        while not entered.is_set():
            await asyncio.sleep(0.005)
        second = asyncio.create_task(agent.blocking(blocking))
        await asyncio.sleep(0.01)
        first.cancel(); second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
        assert len(agent.blocking_tasks) == 2
        with pytest.raises(PlatformError):
            await agent.blocking(lambda: None)
        release.set()
        await asyncio.gather(*list(agent.blocking_tasks))
        await asyncio.sleep(0)
        assert not agent.blocking_tasks
    asyncio.run(scenario())


def test_external_readonly_hint_cannot_bypass_write_replay_guard():
    args = {'sku': 'DEMO-001'}
    agent, _, gateway, identity = setup([tool_call('external__lookup_sku', args, 'first'),
                                        tool_call('external__lookup_sku', args, 'second')])
    gateway.tools[-1].update(name='external__lookup_sku', server_slug='external', annotations={'readOnlyHint': True})
    reply = asyncio.run(agent.run(identity.a, 'question'))
    assert reply['state'] == 'failed' and len(gateway.calls) == 1


@pytest.mark.parametrize('kind', ['retained', 'answer', 'catalog_bytes'])
def test_remaining_byte_limits_are_explicit(kind):
    if kind == 'retained':
        async def large(name, arguments):
            return {'content': [{'type': 'text', 'text': 'x' * 20000}], 'isError': False}
        agent, _, gateway, identity = setup([tool_call(call_id=str(index)) for index in range(7)], large)
    elif kind == 'answer':
        agent, _, gateway, identity = setup([dict(ANSWER, content='x' * 16385)])
    else:
        agent, _, gateway, identity = setup([ANSWER])
        gateway.tools[0]['description'] = 'x' * 65536
    reply = asyncio.run(agent.run(identity.a, 'question'))
    assert reply['state'] == 'limit_reached'
    assert len(gateway.calls) <= 5


def test_today_guard_does_not_reinterpret_third_party_list_orders():
    agent, _, gateway, identity = setup([tool_call('external__list_orders', {}), ANSWER])
    tool = next(tool for tool in gateway.tools if tool['upstream_name'] == 'list_orders')
    tool.update(name='external__list_orders', server_slug='external')
    reply = asyncio.run(agent.run(identity.a, 'today orders elsewhere'))
    assert reply['state'] == 'completed' and gateway.calls[0][2] == {}


def test_today_empty_list_and_exact_midnight_succeed():
    midnight = datetime(2026, 10, 17, 18, 30, tzinfo=timezone.utc)
    window = DayWindow.capture('today', midnight)
    assert window.start == window.end
    agent, _, gateway, identity = setup([tool_call('woocommerce__list_orders', today_arguments()), ANSWER])
    assert asyncio.run(agent.run(identity.a, 'today orders'))['state'] == 'completed'
    assert len(gateway.calls) == 1


@pytest.mark.parametrize('schema', [
    {'type': 'object', 'properties': {'text': {'type': 'string', 'pattern': '(a+)+$'}}},
    {'type': 'object', '$dynamicRef': 'https://metadata.test/schema'},
    {'type': 'object', '$recursiveRef': 'https://metadata.test/schema'},
    {'type': 'object', 'properties': {str(index): {'type': 'string'} for index in range(513)}},
])
def test_unsafe_schema_regex_remote_refs_and_expansion_rejected(schema):
    import time
    started = time.monotonic()
    assert not compatible_schema(schema)
    assert time.monotonic() - started < 0.1


def test_schema_reference_expansion_budget_rejects_reused_tree():
    schema = {'type': 'object', '$defs': {'leaf': {'type': 'string'}}, 'properties': {}}
    previous = 'leaf'
    for index in range(9):
        key = str(index)
        schema['$defs'][key] = {'allOf': [{'$ref': '#/$defs/' + previous}] * 4}
        previous = key
    schema['properties']['value'] = {'$ref': '#/$defs/' + previous}
    assert not compatible_schema(schema)


@pytest.mark.parametrize('code', ['UPSTREAM_UNAVAILABLE', 'UPSTREAM_PROTOCOL_ERROR'])
def test_lost_or_invalid_write_reply_stops_even_modified_model_retry(code):
    first = tool_call('woocommerce__create_product', {'name': 'Mug', 'regular_price': '1.00'}, 'first')
    modified = tool_call('woocommerce__create_product', {'name': 'Another Mug', 'regular_price': '1.00'}, 'retry')
    agent, provider, gateway, identity = setup([first, modified, ANSWER])
    gateway.outcome, gateway.error_code = 'error', code
    reply = asyncio.run(agent.run(identity.a, 'create mug'))
    assert reply['state'] == 'failed' and len(gateway.calls) == len(provider.requests) == 1
    assert 'uncertain' in reply['answer'] and reply['tool_calls'][0]['error_code'] == code


def test_large_duplicate_learn_result_summarizes_ranked_excerpts_without_changing_full_result():
    data = {'results': [
        {'title': f'Kubernetes Pods documentation {index}',
         'content': 'Pods contain one or more containers that share network and storage. ' * 40,
         'contentUrl': f'https://learn.microsoft.com/azure/aks/concepts-clusters-workloads#pods-{index}'}
        for index in range(8)
    ]}
    response = result(data)
    original = copy.deepcopy(response)
    assert len(encoded(data)) < 32 * 1024
    assert len(encoded({'text': [response['content'][0]['text']],
                        'structuredContent': data, 'isError': False})) > 32 * 1024
    direct = json.loads(result_text(response))
    assert direct['structuredContent'] == data and not direct.get('text')
    assert 'chat_excerpt' not in direct

    async def search(name, arguments):
        assert name == 'learn__microsoft_docs_search'
        return response

    async def summarize(messages, tools, final):
        payload = json.loads(messages[-1]['content'])
        assert SEARCH_BUDGET == 4 * 1024
        assert len(messages[-1]['content'].encode('utf-8')) <= SEARCH_BUDGET
        retained = payload['structuredContent']['results']
        assert 0 < len(retained) < len(data['results'])
        assert payload['chat_excerpt'] == {'returned_results': 8, 'retained_results': len(retained)}
        assert [item['contentUrl'] for item in retained] == [item['contentUrl'] for item in data['results'][:len(retained)]]
        assert all(original['content'].startswith(item['content']) and len(item['content'].encode()) <= 384
                   for item, original in zip(retained, data['results']))
        assert not payload.get('text')
        return {'role': 'assistant', 'content': 'Pods group containers. Sources:\n' + '\n'.join(
            item['contentUrl'] for item in payload['structuredContent']['results'])}

    agent, provider, gateway, identity = setup([
        tool_call('learn__microsoft_docs_search', {'query': 'Kubernetes Pods'}), summarize], search)
    tool = copy.deepcopy(gateway.tools[0])
    tool.update(name='learn__microsoft_docs_search', server_slug='learn',
                upstream_name='microsoft_docs_search',
                inputSchema={'type': 'object', 'properties': {'query': {'type': 'string'}},
                             'required': ['query'], 'additionalProperties': False})
    gateway.tools.append(tool)
    reply = asyncio.run(agent.run(identity.a, 'Find official Kubernetes Pods docs and summarise with links.'))
    assert reply['state'] == 'completed' and len(gateway.calls) == 1 and len(provider.requests) == 2
    assert reply['tool_calls'][0]['outcome'] == 'success'
    retained = json.loads(provider.requests[1][0][-1]['content'])['structuredContent']['results']
    assert all(item['contentUrl'] in reply['answer'] for item in retained)
    assert f'Chat used shortened excerpts from {len(retained)} of 8 returned search results; open the links for full text.' in reply['answer']
    assert response == original


def test_duplicate_json_object_order_does_not_change_information_or_source():
    response = {'content': [{'type': 'text', 'text': '{"b":2,"a":1}'}],
                'structuredContent': {'a': 1, 'b': 2}, 'isError': False}
    original = copy.deepcopy(response)
    payload = json.loads(result_text(response))
    assert payload['structuredContent'] == response['structuredContent']
    assert not payload.get('text')
    assert response == original


@pytest.mark.parametrize('text_value,structured_value', [
    ({'value': True}, {'value': 1}),
    ({'value': 1}, {'value': 1.0}),
    ({'title': 'First source'}, {'title': 'Different source'}),
])
def test_different_text_and_structured_json_both_remain_available(text_value, structured_value):
    text = json.dumps(text_value)
    payload = json.loads(result_text({'content': [{'type': 'text', 'text': text}],
                                     'structuredContent': structured_value, 'isError': False}))
    assert payload['text'] == [text]
    assert payload['structuredContent'] == structured_value


def test_multiple_text_blocks_are_not_dropped_as_a_duplicate_structured_result():
    response = {'content': [{'type': 'text', 'text': '{"value":1}'},
                            {'type': 'text', 'text': 'A separate explanatory note.'}],
                'structuredContent': {'value': 1}, 'isError': False}
    payload = json.loads(result_text(response))
    assert payload['text'] == [item['text'] for item in response['content']]
    assert payload['structuredContent'] == {'value': 1}


@pytest.mark.parametrize('text', ['A useful plain-text explanation.', '{"unfinished":', '{"value":NaN}'])
def test_non_json_or_nonstandard_text_remains_available_with_structured_content(text):
    payload = json.loads(result_text({'content': [{'type': 'text', 'text': text}],
                                     'structuredContent': {'value': None}, 'isError': False}))
    assert payload['text'] == [text]
    assert payload['structuredContent'] == {'value': None}


def test_genuinely_oversized_unique_data_still_hits_the_per_tool_limit():
    with pytest.raises(ChatFailure) as failure:
        result_text(result({'content': 'x' * (33 * 1024)}))
    assert failure.value.code == 'CHAT_LIMIT' and failure.value.state == 'limit_reached'


def test_unknown_external_display_failure_warns_about_action_without_retrying():
    async def image(name, arguments):
        return {'content': [{'type': 'image', 'data': 'AA=='}], 'isError': False}
    agent, provider, gateway, identity = setup([
        tool_call('external__lookup_sku', {'sku': 'DEMO-001'}), ANSWER], image)
    gateway.tools[-1].update(name='external__lookup_sku', server_slug='external')
    reply = asyncio.run(agent.run(identity.a, 'Look up the external item.'))
    assert reply['state'] == 'failed' and reply['tool_calls'][0]['outcome'] == 'success'
    assert 'Do not repeat the action without checking its effects.' in reply['answer']
    assert 'Do not repeat the write' not in reply['answer']
    assert len(gateway.calls) == len(provider.requests) == 1


def search_data(count=2):
    return {'results': [{'title': f'Source {index}', 'content': 'x' * 5000,
                         'contentUrl': f'https://learn.microsoft.com/docs/{index}'}
                        for index in range(count)]}


def test_search_excerpt_has_whole_utf8_budget_complete_urls_and_ranked_prefix():
    data = {'results': [{'title': f'{index} ' + '\u092a\u0949\u0921\u094d\u0938' * 30,
                         'content': '\U0001f331' * 200,
                         'contentUrl': f'https://learn.microsoft.com/docs/{index}/' + 'a' * 600}
                        for index in range(14)]}
    response = result(data)
    original = copy.deepcopy(response)
    text = result_text(response, {'upstream_name': 'microsoft_docs_search'})
    payload = json.loads(text)
    assert SEARCH_BUDGET == 4 * 1024
    assert len(text.encode('utf-8')) <= SEARCH_BUDGET
    retained = payload['structuredContent']['results']
    assert 0 < len(retained) < 10
    assert payload['chat_excerpt'] == {'returned_results': 14, 'retained_results': len(retained)}
    for item, source in zip(retained, data['results']):
        assert item['contentUrl'] == source['contentUrl']
        assert source['title'].startswith(item['title']) and len(item['title'].encode('utf-8')) <= 256
        assert source['content'].startswith(item['content']) and len(item['content'].encode('utf-8')) <= 384
        assert '\ufffd' not in item['title'] + item['content']
    assert response == original


@pytest.mark.parametrize('change', ['missing_field', 'extra_field', 'non_string', 'non_object', 'extra_root'])
def test_mixed_or_unknown_search_structure_is_not_silently_excerpted(change):
    data = search_data()
    if change == 'missing_field': del data['results'][1]['contentUrl']
    if change == 'extra_field': data['results'][1]['extra'] = 'unhandled information'
    if change == 'non_string': data['results'][1]['content'] = 42
    if change == 'non_object': data['results'][1] = 'unhandled record'
    if change == 'extra_root': data['metadata'] = {'complete': False}
    payload = json.loads(result_text(result(data), {'upstream_name': 'microsoft_docs_search'}))
    assert 'chat_excerpt' not in payload
    assert payload['structuredContent'] == data


@pytest.mark.parametrize('tool,error', [({'upstream_name': 'other_search'}, False),
                                     ({'upstream_name': 'microsoft_docs_search'}, True)])
def test_search_excerpt_does_not_reinterpret_other_tools_or_error_results(tool, error):
    response = result(search_data())
    response['isError'] = error
    payload = json.loads(result_text(response, tool))
    assert 'chat_excerpt' not in payload
    assert payload['structuredContent'] == response['structuredContent']
    assert payload['isError'] is error


def test_small_search_results_remain_complete_without_excerpt_notice():
    data = {'results': [{'title': 'Pods', 'content': 'A pod groups containers.',
                         'contentUrl': 'https://learn.microsoft.com/docs/pods'}]}
    payload = json.loads(result_text(result(data), {'upstream_name': 'microsoft_docs_search'}))
    assert 'chat_excerpt' not in payload
    assert payload['structuredContent'] == data


def test_search_first_complete_url_cannot_fit_falls_back_without_broken_link():
    data = search_data(1)
    data['results'][0]['contentUrl'] += '/' + 'a' * 9000
    payload = json.loads(result_text(result(data), {'upstream_name': 'microsoft_docs_search'}))
    assert 'chat_excerpt' not in payload
    assert payload['structuredContent'] == data


def test_search_with_additional_text_keeps_both_representations_instead_of_excerpting():
    data = search_data()
    response = {'content': [{'type': 'text', 'text': 'Important separate explanation.'}],
                'structuredContent': data, 'isError': False}
    payload = json.loads(result_text(response, {'upstream_name': 'microsoft_docs_search'}))
    assert 'chat_excerpt' not in payload
    assert payload['text'] == ['Important separate explanation.']
    assert payload['structuredContent'] == data


def rate_limit(delay=.001):
    return ChatFailure('PROVIDER_RATE_LIMIT', 'The language model rate limit was reached.', retry_after=delay)


def test_one_delayed_provider_completion_retry_keeps_identical_context_without_replaying_tool():
    agent, provider, gateway, identity = setup([tool_call(), rate_limit(), ANSWER])
    reply = asyncio.run(agent.run(identity.a, 'Find the sample inventory.'))
    assert reply['state'] == 'completed'
    assert len(gateway.calls) == 1 and len(provider.requests) == 3
    assert provider.requests[1] == provider.requests[2]
    assert 'rate limit' in reply['answer'].lower()


def test_initial_planning_rate_limit_is_not_retried():
    agent, provider, gateway, identity = setup([rate_limit(), ANSWER])
    reply = asyncio.run(agent.run(identity.a, 'Find the sample inventory.'))
    assert reply['state'] == 'failed' and len(provider.requests) == 1 and gateway.calls == []


@pytest.mark.parametrize('error', [rate_limit(None),
    ChatFailure('PROVIDER_UNAVAILABLE', 'Model unavailable.', retry_after=.001)])
def test_missing_wait_hint_or_other_provider_failure_after_tool_is_not_retried(error):
    agent, provider, gateway, identity = setup([tool_call(), error, ANSWER])
    reply = asyncio.run(agent.run(identity.a, 'Find the sample inventory.'))
    assert reply['state'] == 'failed' and len(provider.requests) == 2 and len(gateway.calls) == 1


def test_second_rate_limit_does_not_start_an_unbounded_retry_loop():
    agent, provider, gateway, identity = setup([tool_call(), rate_limit(), rate_limit(), ANSWER])
    reply = asyncio.run(agent.run(identity.a, 'Find the sample inventory.'))
    assert reply['state'] == 'failed' and len(provider.requests) == 3 and len(gateway.calls) == 1


def test_separate_completion_rounds_can_each_wait_once_without_replaying_tools():
    agent, provider, gateway, identity = setup([
        tool_call(call_id='first'), rate_limit(), tool_call(call_id='second'), rate_limit(), ANSWER])
    reply = asyncio.run(agent.run(identity.a, 'Check sample inventory.'))
    assert reply['state'] == 'completed' and len(provider.requests) == 5 and len(gateway.calls) == 2
    assert provider.requests[1] == provider.requests[2]
    assert provider.requests[3] == provider.requests[4]
    assert [call[1] for call in gateway.calls] == ['inventory__lookup_sku', 'inventory__lookup_sku']


def test_per_completion_waits_preserve_fifteen_attempt_and_eight_round_ceiling():
    replies = [tool_call(call_id='first')]
    for index in range(1, 7):
        replies.extend([rate_limit(), tool_call(call_id=str(index))])
    replies.extend([rate_limit(), ANSWER])
    agent, provider, gateway, identity = setup(replies)
    reply = asyncio.run(agent.run(identity.a, 'Check sample inventory.'))
    assert reply['state'] == 'completed' and len(provider.requests) == 15 and len(gateway.calls) == 7
    assert provider.requests[0][2] is False
    for index in range(1, 15, 2):
        assert provider.requests[index] == provider.requests[index + 1]
    assert provider.requests[-1][2] is True


def test_later_completion_wait_cannot_reset_the_shared_chat_deadline():
    agent, provider, gateway, identity = setup([
        tool_call(call_id='first'), rate_limit(1.2), tool_call(call_id='second'), rate_limit(1.2), ANSWER],
        deadline=2)
    reply = asyncio.run(agent.run(identity.a, 'Check sample inventory.'))
    assert reply['state'] == 'failed' and len(provider.requests) == 4 and len(gateway.calls) == 2
    assert 'rate limit' in reply['answer'].lower()
    assert agent.active == 0


def test_final_completion_single_retry_preserves_final_mode_and_exact_attempt_count():
    replies = [tool_call(call_id=str(index)) for index in range(7)] + [rate_limit(), ANSWER]
    agent, provider, gateway, identity = setup(replies)
    reply = asyncio.run(agent.run(identity.a, 'Check sample inventory.'))
    assert reply['state'] == 'completed' and len(provider.requests) == 9 and len(gateway.calls) == 7
    assert provider.requests[-2] == provider.requests[-1] and provider.requests[-1][2] is True


def test_rate_wait_longer_than_remaining_deadline_is_not_started():
    agent, provider, gateway, identity = setup([tool_call(), rate_limit(3), ANSWER], deadline=2)
    reply = asyncio.run(agent.run(identity.a, 'Check sample inventory.'))
    assert reply['state'] == 'failed' and len(provider.requests) == 2 and len(gateway.calls) == 1
    assert 'rate limit' in reply['answer'].lower()
    assert agent.active == 0


def test_allowed_rate_wait_does_not_extend_deadline_for_the_completion_retry():
    async def stall(*args):
        await asyncio.sleep(10)
    agent, provider, gateway, identity = setup([tool_call(), rate_limit(), stall], deadline=2)
    reply = asyncio.run(agent.run(identity.a, 'Check sample inventory.'))
    assert reply['state'] == 'limit_reached' and len(provider.requests) == 3 and len(gateway.calls) == 1
    assert agent.active == 0


def test_identity_revocation_during_rate_wait_blocks_provider_retry():
    async def scenario():
        entered = asyncio.Event()
        async def limited(*args):
            entered.set()
            raise rate_limit(.05)
        agent, provider, gateway, identity = setup([tool_call(), limited, ANSWER])
        async def revoke():
            await entered.wait()
            identity.valid.clear()
        revoker = asyncio.create_task(revoke())
        reply = await agent.run(identity.a, 'Check sample inventory.')
        await revoker
        assert reply['state'] == 'failed' and len(provider.requests) == 2 and len(gateway.calls) == 1
    asyncio.run(scenario())


def test_cancel_during_rate_wait_stops_without_provider_or_tool_replay():
    async def scenario():
        entered = asyncio.Event()
        async def limited(*args):
            entered.set()
            raise rate_limit(30)
        agent, provider, gateway, identity = setup([tool_call(), limited, ANSWER])
        task = asyncio.create_task(agent.run(identity.a, 'Check sample inventory.'))
        await entered.wait()
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert agent.active == 0 and len(provider.requests) == 2 and len(gateway.calls) == 1
    asyncio.run(scenario())
