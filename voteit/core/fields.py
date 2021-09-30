from django.db import models
from typing import Callable


class RichTextField(models.TextField):
    html_cleaner: Callable[[str], str]

    def __init__(self, html_cleaner: Callable[[str], str] = None, *args, **kwargs):
        if html_cleaner is None:
            from voteit.core.utils import strict_clean_html

            html_cleaner = strict_clean_html
        self.html_cleaner = html_cleaner
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add) -> str:
        value = super().pre_save(model_instance, add)
        cleaned_value = self.html_cleaner(value)
        if cleaned_value != value:
            setattr(model_instance, self.attname, cleaned_value)
        return cleaned_value
