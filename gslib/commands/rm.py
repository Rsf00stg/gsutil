# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import boto

from gslib.command import Command
from gslib.command import COMMAND_NAME
from gslib.command import COMMAND_NAME_ALIASES
from gslib.command import CONFIG_REQUIRED
from gslib.command import FILE_URIS_OK
from gslib.command import MAX_ARGS
from gslib.command import MIN_ARGS
from gslib.command import PROVIDER_URIS_OK
from gslib.command import SUPPORTED_SUB_ARGS
from gslib.command import URIS_START_ARG
from gslib.command import XML_PARSE_REQUIRED
from gslib.exception import CommandException
from gslib import wildcard_iterator
from gslib.thread_pool import ThreadPool
from gslib.util import DEFAULT_PARALLEL_THREAD_COUNT
from gslib.util import NO_MAX

class RmCommand(Command):
  """Implementation of gsutil rm command."""

  # Command specification (processed by parent class).
  command_spec = {
    # Name of command.
    COMMAND_NAME : 'rm',
    # List of command name aliases.
    COMMAND_NAME_ALIASES : ['del', 'delete', 'remove'],
    # Min number of args required by this command.
    MIN_ARGS : 1,
    # Max number of args required by this command, or NO_MAX.
    MAX_ARGS : NO_MAX,
    # Getopt-style string specifying acceptable sub args.
    SUPPORTED_SUB_ARGS : 'f',
    # True if file URIs acceptable for this command.
    FILE_URIS_OK : False,
    # True if provider-only URIs acceptable for this command.
    PROVIDER_URIS_OK : False,
    # Index in args of first URI arg.
    URIS_START_ARG : 0,
    # True if must configure gsutil before running command.
    CONFIG_REQUIRED : True,
    # True if this command requires XML parsing.
    XML_PARSE_REQUIRED : False
  }

  # Command entry point.
  def RunCommand(self):
    continue_on_error = False
    if self.sub_opts:
      for o, unused_a in self.sub_opts:
        if o == '-f':
          continue_on_error = True

    # Used to track if any files failed to be removed.
    self.everything_removed_okay = True

    def _RemoveExceptionHandler(e):
      """Simple exception handler to allow post-completion status."""
      self.THREADED_LOGGER.error(str(e))
      self.everything_removed_okay = False

    def _RemoveFunc(uri, uri_str):
      if uri.names_container():
        if uri.is_cloud_uri():
          # Before offering advice about how to do rm + rb, ensure those
          # commands won't fail because of bucket naming problems.
          boto.s3.connection.check_lowercase_bucketname(uri.bucket_name)
        uri_str = uri_str.rstrip('/\\')
        raise CommandException('"rm" command will not remove buckets. To '
                               'delete this/these bucket(s) do:\n\tgsutil rm '
                               '%s/*\n\tgsutil rb %s' % (uri_str, uri_str))
      self.THREADED_LOGGER.info('Removing %s...', uri)
      uri.delete_key(validate=False, headers=self.headers)

    if self.parallel_operations:
      thread_count = boto.config.getint(
          'GSUtil', 'parallel_thread_count', DEFAULT_PARALLEL_THREAD_COUNT)
      thread_pool = ThreadPool(thread_count, _RemoveExceptionHandler)

    try:
      # Expand object name wildcards, if any.
      for uri_str in self.args:
        for uri in self.CmdWildcardIterator(uri_str):
          if self.parallel_operations:
            thread_pool.AddTask(_RemoveFunc, uri, uri_str)
          else:
            try:
              _RemoveFunc(uri, uri_str)
            except Exception, e:
              if continue_on_error:
                self.THREADED_LOGGER.error(str(e))
              else:
                raise e
      if self.parallel_operations:
        thread_pool.WaitCompletion()
    finally:
      if self.parallel_operations:
        thread_pool.Shutdown()
