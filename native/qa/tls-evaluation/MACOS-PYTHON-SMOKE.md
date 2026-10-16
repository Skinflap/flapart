# Mac SDK Python import smoke correction

Run 38901174930 reached successful DESTDIR installation and reported no missing baseline extensions. Its `tls/11-build-python.log` then failed importing SDK `PyQt5.QtCore.abi3.so`: dyld could not resolve `@rpath/QtCore.framework/Versions/5/QtCore`. The binding is nested inside SDK Python.framework; its relative rpath does not reach SDK/lib. `run-native-ci.py` sets the SDK framework loader environment only after this builder returns, so that later environment cannot help this smoke.

The builder now derives SDK/lib from the supplied, resolved framework-contained site-packages path and requires its QtCore binary. Only the smoke subprocess gets explicit loader paths. Newly built Python.framework precedes SDK frameworks, with maintained OpenSSL libraries first in the dylib search path. Inherited DYLD overrides and PYTHONHOME/PYTHONPATH are replaced for this subprocess. No binary load commands, global environment, runtime packaging, TLS validation, or final relocation checks are changed.

The receipt labels this as SDK build-time smoke. It requires Python 3.13.16, the expected new sys.prefix, and Apple's dyld image list showing exactly the new Python framework; it records actual PyQt QtCore module path, Qt/OpenSSL versions, and certificate defaults. The PyQt module must be under the supplied site-packages. This prevents an old SDK interpreter from making the smoke appear successful.

Five local helper tests pass: loader precedence/override removal, resolved SDK alias, and refusal of missing QtCore, missing new Python, or unrelated site-packages. Python syntax compilation passes. These tests validate environment construction only; native Mac rerun remains required. No CI, mirror, or workflow changes were made.
