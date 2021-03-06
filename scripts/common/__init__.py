'''
EXPERIMENTAL: this is a demonstrator and not the final product!
This module provides the common pieces for scripts wrapping around clang(++)
invocations which allows to invoke static analysis if certain environment
variables are set.
Tested with ROOT

In order to steer SA within your setup (your laptop, Jenknins or whatever CI
system) the following variables must be defined:
o SA_CHECKERS: list of checkers names separated by a ":", a la PATH.
  Example: SA_CHECKERS="core.uninitialized:cplusplus"
o SA_CLANG_CPP: path to clang++. This is the compiler to be called to perform
  static analysis.
  Example: SA_CLANG_CPP=/afs/cern.ch/sw/blaBlaBla/clang35/blaBlaBla/bin/clang++
o SA_PLUGIN: plugin library of custom checkers, for example built with SAS.
  https://indico.cern.ch/event/267747/contribution/2/1/material/slides/0.pdf
  Example: SA_PLUGIN="/path/to/my/libSas.so"
o SA_FORMATTING: if this is defined, formatting rules are checked
'''

from __future__ import print_function

import subprocess
import difflib
import sys
import os
import shutil

_ClangFormatExeName="@@@clang-format"
_ClangModernizeExeName="@@@clang-modernize"
_SourceFilesExtensions=[".cpp",".cxx",".c",
                        ".h",".hpp",".icc",".hxx"]
_SourceFilesExtensions+=map(str.upper,_SourceFilesExtensions)

def _Purple(text):
   '''
   Make this text violet
   '''
   return "\033[35m%s \033[m" %text

def _Bold(text):
   '''
   Guess...
   '''
   return "\033[1m%s \033[m" %text

def _WrapClangCommand(command, SA_CLANG_COMPILER):
   '''
   Wrap the compilation command and force clang to run static analysis.
   Invoke SA and compilation
   '''
   SA_CHECKERS = "SA_CHECKERS"
   SA_PLUGIN = "SA_PLUGIN"
   BASE_XCLANG_ARGS = ["-Xclang", "-analyze", "-Xclang", "-analyzer-output=text"]

   env = os.environ
   sa_checkersString = env[SA_CHECKERS] if env.has_key(SA_CHECKERS) else ""
   sa_checkers = filter(lambda name: name!='', sa_checkersString.split(":"))
   compilerArguments = command[1:]

   if len(sa_checkers)>0 and "-c" in compilerArguments and not "-shared" in compilerArguments:
      sa_plugin = env[SA_PLUGIN] if env.has_key(SA_PLUGIN) else ""
      # Accumulate checkers names
      checkers_args=[]
      for checkerName in sa_checkers:
         checkers_args += ["-Xclang", "-analyzer-checker=%s" %checkerName]

      # Load the plugin if one has been specified
      plugin_args=[]
      if sa_plugin != "":
         plugin_args += ["-Xclang", "-load", "-Xclang", "%s" %sa_plugin]


      outputToNull = ["-o","/dev/null"]

      # Recompose the SA command
      saCommand = [SA_CLANG_COMPILER] + \
                  BASE_XCLANG_ARGS + \
                  checkers_args + \
                  plugin_args + \
                  compilerArguments + \
                  outputToNull

      #print ("note:", "Invoking SA with command %s " %(" ".join(saCommand)), file=sys.stdout)
      subprocess.call(saCommand)

   return subprocess.call(command)

def _CompareFiles(filename, clangFormatOutput, outputType):
    '''
    Compare the formatted version of the file with the existing one.
    '''
    fileContentLines = open(filename,"r").read().splitlines()
    clangFormatOutputLines = clangFormatOutput.splitlines()

    diffLinesGen = difflib.context_diff(fileContentLines,
                                        clangFormatOutputLines,
                                        fromfile='Original File (%s)' %filename,
                                        tofile='Formatted File')
    diffLines = list(diffLinesGen)
    nViolations = int ( sum(0.5 for line in diffLines if line[0] == '!') )

    # Here we should put some mechanism to display violations as warnings to
    # integrate this script in CI systems, think to the jenkins warning parsers.
    # In addition if nViolations is greater than some number we could just print
    # an error.
    if nViolations >0 :
        plural = "" if nViolations == 1 else "s"
        print (_Bold(_Purple("warning:")), _Bold('%s %s%s detected.' %(nViolations,outputType,plural)), file=sys.stderr)
        print ("\n".join(diffLines), file=sys.stderr)
    return nViolations

def _RunClangCommand(command, filename):
    '''
    Run clang-format and capture output
    '''
    process = subprocess.Popen([command,filename], stdout=subprocess.PIPE)
    result = process.communicate()[0]
    return result

def _RunClangModernize(command, filename, options):
    '''
    Run clang-modernize and capture output
    '''
    basename=os.path.basename(filename)
    tempname=basename[:basename.rfind('.')] + '.temp' + basename[basename.rfind('.'):]
    dirname=os.path.dirname(filename)
    tempfile=os.path.join(dirname, tempname)

    shutil.copyfile(filename, tempfile)
    optionsList = options.split(' ')

    process = subprocess.Popen([command] + optionsList + [tempfile], stdout = subprocess.PIPE)
    process.communicate()[0]
    resultFile = open(tempfile, 'r')
    result = resultFile.read()
    resultFile.close()
    os.remove(tempname)
    return result

def CheckFormattingRules(filename):
    '''
    Check the formatting rules
    '''
    clangFormatOutput = _RunClangCommand(_ClangFormatExeName, filename)
    nViolations = _CompareFiles(filename, clangFormatOutput, 'code formatting rules violation')

def ClangModernize(options, filename):
    '''
    Run clang-modernize on sources
    '''
    clangModernizeOutput = _RunClangModernize(_ClangModernizeExeName, filename, options)
    nViolations = _CompareFiles(filename, clangModernizeOutput, 'available clang-modernize transformation')

def _IsSourceFile(filename):
    '''
    Return true in case this filename is a source
    '''
    fileExtension = os.path.splitext(filename)[1]
    return fileExtension in _SourceFilesExtensions

def Analyze(command, sa_clang_compiler):
    '''
    Perform static analysis and check of formatting rules if requested
    '''
    returnVal=0
    sources = filter(_IsSourceFile, command)
    if os.environ.has_key("SA_FORMATTING"):
       res = map(CheckFormattingRules, sources)
       returnVal = len(res)
    if os.environ.has_key("SA_MODERNIZE"):
       options = os.environ['SA_MODERNIZE']
       res = map(lambda source: ClangModernize(options,source), sources)
       returnVal = len(res)


    returnVal += _WrapClangCommand(command, sa_clang_compiler)
    return returnVal
