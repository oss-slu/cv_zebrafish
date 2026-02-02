from setuptools import setup, find_packages

# Manually specify packages to map src/ contents to cvzebrafish namespace
packages = [
    'cvzebrafish',
    'cvzebrafish.core',
    'cvzebrafish.core.calculations',
    'cvzebrafish.core.config',
    'cvzebrafish.core.graphs',
    'cvzebrafish.core.parsing',
    'cvzebrafish.core.validation',
    'cvzebrafish.app_platform',
    'cvzebrafish.data',
    'cvzebrafish.session',
    'cvzebrafish.ui',
    'cvzebrafish.ui.components',
    'cvzebrafish.ui.scenes',
]

package_dir = {
    'cvzebrafish': 'src',
    'cvzebrafish.core': 'src/core',
    'cvzebrafish.core.calculations': 'src/core/calculations',
    'cvzebrafish.core.config': 'src/core/config',
    'cvzebrafish.core.graphs': 'src/core/graphs',
    'cvzebrafish.core.parsing': 'src/core/parsing',
    'cvzebrafish.core.validation': 'src/core/validation',
    'cvzebrafish.app_platform': 'src/app_platform',
    'cvzebrafish.data': 'src/data',
    'cvzebrafish.session': 'src/session',
    'cvzebrafish.ui': 'src/ui',
    'cvzebrafish.ui.components': 'src/ui/components',
    'cvzebrafish.ui.scenes': 'src/ui/scenes',
}

setup(
    name="cvzebrafish",
    version="0.1.0",
    description="Desktop toolkit for validating DeepLabCut zebrafish CSVs",
    packages=packages,
    package_dir=package_dir,
    python_requires=">=3.10",
    install_requires=[
        "PyQt5>=5.15.0",
        "pytest>=7.0.0",
        "plotly>=5.0.0",
        "kaleido",
        "pandas",
        "numpy",
    ],
)