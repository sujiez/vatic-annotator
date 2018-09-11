# Vatic++ video annotator

First install the [vatic server](https://github.com/johndoherty/vatic)

Second, replace all essential files in the local vatic_bb folder with files in vatic_local_side folder.

Third, replace all essential files in usr/local/lib/python2.7/dist-packages/turkic-0.2.5-py2.7.egg/turkic with files in usr_local_lib_python2.7_dist-packages_turkic-0.2.5-py2.7.egg.

Forth, install the [re3 tracker](https://gitlab.cs.washington.edu/xkcd/re3-tensorflow) and make sure it works properly (only need the reference mode, no training need). 

Fifth, modify re3_server to give the right path of re3 tracker.

Finally, restart the whole server and run the python file in re3_server.
