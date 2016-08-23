from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os


class OverwriteStorage(FileSystemStorage):

    def get_available_name(self, name):
        """Returns a filename that's free on the target storage system, and
        available for new content to be written to.

        Found at http://djangosnippets.org/snippets/976/

        This file storage solves overwrite on upload problem. Another
        proposed solution was to override the save method on the model
        like so (from https://code.djangoproject.com/ticket/11663):

        def save(self, *args, **kwargs):
            try:
                this = MyModelName.objects.get(id=self.id)
                if this.MyImageFieldName != self.MyImageFieldName:
                    this.MyImageFieldName.delete()
            except: pass
            super(MyModelName, self).save(*args, **kwargs)
        """
        # If the filename already exists, remove it as if it was a true file system

        # if os.path.isfile(os.path.join(settings.BASE_DIR, 'graphs', uuid+'_fourth.json')):
        #     os.remove(os.path.join(settings.BASE_DIR, 'graphs', uuid+'_fourth.json'))
        #
        # suffixes = ['third', 'second', 'first']
        # suffixes_next = ['fourth', 'third', 'second']
        #
        # for suffix in suffixes:
        #     for filename in os.listdir(os.path.join(settings.BASE_DIR, 'graphs')):
        #         if filename.startswith(uuid):
        #             if filename.endswith(suffix+'.json'):
        #                 new_name = "%s_%s.json" % (uuid, suffixes_next[suffixes.index(suffix)])
        #                 os.rename(os.path.join(settings.BASE_DIR, 'graphs', filename), os.path.join(settings.BASE_DIR, 'graphs', new_name))
        #
        # for filename in os.listdir(os.path.join(settings.BASE_DIR, 'graphs')):
        #     if filename == uuid+'.json':
        #         os.rename(os.path.join(settings.BASE_DIR, 'graphs', filename), os.path.join(settings.BASE_DIR, 'graphs', uuid+'_first.json'))

        if self.exists(name):
            os.remove(os.path.join(settings.MEDIA_ROOT, name))
        return name