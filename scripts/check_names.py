"""Catch NameErrors that only fire at runtime (e.g. DISPLAY_NAME used but not imported).

For every module: collect module-level bindings (imports, defs, assignments,
class names), then walk each function body for Name loads that are neither
local bindings, arguments, enclosing-closure bindings, module-level bindings,
nor builtins. Nested function bodies are skipped so their own args/locals are
judged separately.

Usage:
    python3 scripts/check_names.py custom_components/yujian/*.py

Why this exists: v1.1.1 shipped an options flow that used DISPLAY_NAME without
importing it. py_compile passed, the integration loaded, notifications worked --
and the "Configure" button returned HTTP 500 only when a user opened it. No
packaged linter is required, so this runs anywhere.
"""
import ast
import builtins
import sys

BUILTINS = set(dir(builtins))


def collect_module_bindings(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split('.')[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.If, ast.Try)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        names.add((alias.asname or alias.name).split('.')[0])
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
    return names


def local_bindings(func):
    names = set()
    for a in list(func.args.args) + list(func.args.kwonlyargs) + list(func.args.posonlyargs):
        names.add(a.arg)
    if func.args.vararg:
        names.add(func.args.vararg.arg)
    if func.args.kwarg:
        names.add(func.args.kwarg.arg)
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split('.')[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.comprehension,)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    names.add(n.id)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            for n in ast.walk(node.optional_vars):
                if isinstance(n, ast.Name):
                    names.add(n.id)
    return names


def check(path):
    src = open(path, encoding='utf-8').read()
    tree = ast.parse(src, path)
    module_names = collect_module_bindings(tree)

    # map every node to its enclosing functions, so closure variables
    # (names bound in an ancestor function) are not reported as undefined
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def enclosing_scopes(node):
        scope = node
        while scope is not None:
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield scope
            scope = parents.get(scope)

    def body_names(func):
        """Name loads directly owned by this function, excluding nested scopes."""
        out = []

        def walk(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue  # checked on its own, with its own args/locals
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    out.append(child)
                walk(child)

        walk(func)
        return out

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        visible = set()
        for scope in enclosing_scopes(node):
            visible |= local_bindings(scope)
        for sub in body_names(node):
            if (sub.id not in visible and sub.id not in module_names
                    and sub.id not in BUILTINS):
                problems.append((path, sub.lineno, node.name, sub.id))
    return problems


if __name__ == '__main__':
    found = []
    for p in sys.argv[1:]:
        found.extend(check(p))
    if not found:
        print('OK: 没有未定义的模块级名字')
    for path, line, func, name in found:
        print(f'{path}:{line}: 在 {func}() 里使用了未定义的名字 {name!r}')
    sys.exit(1 if found else 0)
