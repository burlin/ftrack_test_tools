# Contributing to Mroya Project

## Code Comments Language

**All code comments must be written in English.**

This rule applies to:
- Inline comments explaining code logic
- Function and class docstrings
- TODO, FIXME, and NOTE comments
- Multi-line block comments
- Code documentation

### Why English?

- **International collaboration**: Team members may speak different languages
- **Consistency**: Ensures uniform codebase style
- **Maintainability**: Easier for future developers to understand
- **Industry standard**: Most open-source projects use English for code comments

### Examples

✅ **Correct:**
```python
# Filter events by current user and workstation
topic_filter = (
    'topic=mroya.transfer.request and '
    'source.user.username="{0}" and '
    'source.id="{1}"'
).format(current_user, current_event_hub_id)

def process_transfer_request(event):
    """Process a transfer request event.
    
    This function handles incoming transfer requests and validates
    that they are intended for the current user and workstation.
    
    Args:
        event: Ftrack event object containing transfer request data
        
    Returns:
        bool: True if request was processed successfully
    """
    pass
```

❌ **Incorrect:**
```python
# Фильтруем события по текущему пользователю и рабочей станции
topic_filter = ...

def process_transfer_request(event):
    """Обрабатывает запрос на трансфер.
    
    Эта функция обрабатывает входящие запросы на трансфер...
    """
    pass
```

## Code Style Guidelines

- Follow **PEP 8** for Python code formatting
- Use **type hints** for function parameters and return values
- Write **descriptive variable names** (avoid abbreviations unless widely understood)
- Keep functions **focused and single-purpose**
- Add **comprehensive error handling** with meaningful error messages
- Use **docstrings** for all public functions and classes

## Commit Messages

- Write commit messages in English
- Use clear, descriptive commit messages
- Follow conventional commit format when possible:
  - `feat: add user filtering to transfer manager`
  - `fix: resolve cross-user task execution issue`
  - `docs: update contributing guidelines`

## Pull Requests

- Write PR descriptions in English
- Explain what changes were made and why
- Reference related issues if applicable
- Ensure all tests pass before submitting
