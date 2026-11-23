"""Explicit read capability list; new routes are denied until reviewed."""
import re

# These handlers only consult existing records/documents. Preview, generation,
# synchronization and editing endpoints are deliberately NOT capabilities.
READ_PATHS = (
    r'/', r'/gantt/?', r'/gantt/data', r'/properties/?', r'/properties/\d+',
    r'/rooms/\d+', r'/rooms/property/\d+', r'/persons', r'/persons/options',
    r'/persons/\d+', r'/owners', r'/owners/\d+', r'/expenses', r'/expenses/\d+',
    r'/settlements', r'/settlements/\d+', r'/settlements/\d+/documents/\d+',
    r'/bookings/\d+', r'/bookings/room/\d+', r'/bookings/\d+/people',
    r'/bookings/\d+/finance', r'/media-assets/\d+/variants/\d+',
    r'/static/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+',
)
READ_POSTS = frozenset({'/bookings/person-search'})


def permits(method, path):
    if method == 'POST':
        return path in READ_POSTS
    return method in {'GET', 'HEAD'} and any(re.fullmatch(p, path) for p in READ_PATHS)


def capability(method, path):
    if method == 'POST' and path in READ_POSTS:
        return '/bookings/person-search'
    return next((p for p in READ_PATHS if re.fullmatch(p, path)), '/{denied}')
