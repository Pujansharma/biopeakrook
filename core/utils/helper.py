def response_format(detail, data=None):
    context = {'detail': detail}
    if data is not None:
        if all(key in data for key in ['count', 'next', 'previous', 'results']):
            results = data.pop('results')
            return {**context, **data, 'data': results}
        return {**context, 'data': data}
    return context
