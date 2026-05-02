"""Zig language extractor."""

from __future__ import annotations

import tree_sitter_zig as tszig
from tree_sitter import Language, Parser
from tree_sitter import Node as TSNode

from smg.hashing import content_hash, structure_hash
from smg.langs import ExtractResult, register
from smg.metrics import BranchMap, compute_metrics_and_hash
from smg.model import Edge, Node, NodeType, RelType


def _node_text(node: TSNode) -> str:
    return (node.text or b"").decode()


_LANGUAGE = Language(tszig.language())
_PARSER = Parser(_LANGUAGE)

ZIG_BRANCH_MAP = BranchMap(
    branch_nodes=frozenset(
        {
            "if_statement",
            "if_expression",
            "else_clause",
            "for_statement",
            "while_statement",
            "while_expression",
            "switch_expression",
            "switch_case",
            "catch_expression",
            "try_expression",
        }
    ),
    boolean_operators=frozenset({"binary_expression"}),
    nesting_nodes=frozenset(
        {
            "if_statement",
            "if_expression",
            "for_statement",
            "while_statement",
            "while_expression",
            "switch_expression",
        }
    ),
    loop_nodes=frozenset({"for_statement", "while_statement", "while_expression"}),
    function_nodes=frozenset({"function_declaration"}),
    logical_operator_tokens=frozenset({"and", "or"}),
)

_BUILTINS = frozenset(
    {
        "std",
        "print",
        "assert",
        "expect",
        "log",
    }
)

_CONSTRUCTOR_FUNCTIONS = frozenset({"init"})


class ZigExtractor:
    extensions = [".zig"]
    branch_map = ZIG_BRANCH_MAP

    def extract(self, source: bytes, file_path: str, module_name: str) -> ExtractResult:
        tree = _PARSER.parse(source)
        nodes: list[Node] = []
        edges: list[Edge] = []
        self._walk_top_level(tree.root_node, source, module_name, file_path, nodes, edges)
        self._extract_imports(tree.root_node, module_name, edges)
        return ExtractResult(nodes=nodes, edges=edges)

    def _walk_top_level(
        self,
        root: TSNode,
        source: bytes,
        module_name: str,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        for child in root.children:
            if child.type == "variable_declaration":
                self._extract_variable_decl(child, source, module_name, file_path, nodes, edges)
            elif child.type == "function_declaration":
                self._extract_function(child, source, module_name, None, file_path, nodes, edges)
            elif child.type == "test_declaration":
                self._extract_test(child, module_name, file_path, nodes, edges)

    def _extract_variable_decl(
        self,
        node: TSNode,
        source: bytes,
        parent_name: str,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        name_node = _find_child(node, "identifier")
        if name_node is None:
            return
        var_name = _node_text(name_node)

        # Check if it's a struct declaration
        struct_node = _find_child(node, "struct_declaration")
        if struct_node is not None:
            self._extract_struct(struct_node, source, var_name, parent_name, file_path, nodes, edges)
            return

        # Check if it's an enum or union
        enum_node = _find_child(node, "enum_declaration")
        if enum_node is not None:
            qualified = f"{parent_name}.{var_name}"
            nodes.append(
                Node(
                    name=qualified,
                    type=NodeType.TYPE,
                    file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
            edges.append(Edge(source=parent_name, target=qualified, rel=RelType.CONTAINS))
            return

        # UPPER_CASE = constant
        if var_name.isupper() or (var_name[0].isupper() and "_" in var_name and var_name == var_name.upper()):
            qualified = f"{parent_name}.{var_name}"
            nodes.append(
                Node(
                    name=qualified,
                    type=NodeType.CONSTANT,
                    file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
            edges.append(Edge(source=parent_name, target=qualified, rel=RelType.CONTAINS))

    def _extract_struct(
        self,
        struct_node: TSNode,
        source: bytes,
        struct_name: str,
        parent_name: str,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        qualified = f"{parent_name}.{struct_name}"
        nodes.append(
            Node(
                name=qualified,
                type=NodeType.CLASS,  # Zig structs map to class in smg
                file=file_path,
                line=struct_node.start_point[0] + 1,
                end_line=struct_node.end_point[0] + 1,
                metadata={
                    "content_hash": content_hash(source, struct_node.start_byte, struct_node.end_byte),
                    "structure_hash": structure_hash(struct_node),
                },
            )
        )
        edges.append(Edge(source=parent_name, target=qualified, rel=RelType.CONTAINS))

        # Walk struct body for methods and fields
        for child in struct_node.children:
            if child.type == "function_declaration":
                self._extract_function(child, source, qualified, qualified, file_path, nodes, edges)
            elif child.type == "variable_declaration":
                self._extract_variable_decl(child, source, qualified, file_path, nodes, edges)

    def _extract_function(
        self,
        node: TSNode,
        source: bytes,
        parent_name: str,
        struct_name: str | None,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        name_node = _find_child(node, "identifier")
        if name_node is None:
            return
        func_name = _node_text(name_node)
        qualified = f"{parent_name}.{func_name}"

        # Detect if this is a method (has self parameter)
        is_method = self._has_self_param(node)

        meta = compute_metrics_and_hash(node, self.branch_map)

        nodes.append(
            Node(
                name=qualified,
                type=NodeType.METHOD if is_method else NodeType.FUNCTION,
                file=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                metadata={
                    "metrics": meta.metrics.to_dict(),
                    "content_hash": content_hash(source, node.start_byte, node.end_byte),
                    "structure_hash": meta.structure_hash,
                },
            )
        )
        edges.append(Edge(source=parent_name, target=qualified, rel=RelType.CONTAINS))

        # Extract calls from function body
        body = _find_child(node, "block")
        if body is not None:
            receiver_types = self._collect_receiver_types(body)
            self._extract_calls(body, qualified, struct_name if is_method else None, edges, receiver_types)

    def _extract_test(
        self,
        node: TSNode,
        module_name: str,
        file_path: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        """Extract test declarations as function nodes."""
        # Test name is a string literal
        string_node = _find_child(node, "string")
        if string_node is None:
            return
        content = _find_child(string_node, "string_content")
        if content is None:
            return
        test_name = _node_text(content).replace(" ", "_")
        qualified = f"{module_name}.test_{test_name}"

        nodes.append(
            Node(
                name=qualified,
                type=NodeType.FUNCTION,
                file=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                metadata={"test": True},
            )
        )
        edges.append(Edge(source=module_name, target=qualified, rel=RelType.CONTAINS))

    def _extract_imports(
        self,
        root: TSNode,
        module_name: str,
        edges: list[Edge],
    ) -> None:
        """Extract @import() calls as IMPORTS edges."""
        self._find_imports_recursive(root, module_name, edges)

    def _find_imports_recursive(self, node: TSNode, module_name: str, edges: list[Edge]) -> None:
        if node.type == "builtin_function":
            builtin_id = _find_child(node, "builtin_identifier")
            if builtin_id is not None and builtin_id.text == b"@import":
                args = _find_child(node, "arguments")
                if args is not None:
                    string_node = _find_child(args, "string")
                    if string_node is not None:
                        content = _find_child(string_node, "string_content")
                        if content is not None:
                            target = _node_text(content)
                            edges.append(
                                Edge(
                                    source=module_name,
                                    target=target,
                                    rel=RelType.IMPORTS,
                                    metadata={"unresolved": True},
                                )
                            )
                return
        for child in node.children:
            # Only scan top-level variable declarations for imports
            if node.type == "source_file" or node.type == "variable_declaration" or node.type == "field_expression":
                self._find_imports_recursive(child, module_name, edges)

    def _extract_calls(
        self,
        root: TSNode,
        caller_name: str,
        struct_name: str | None,
        edges: list[Edge],
        receiver_types: dict[str, list[str]],
    ) -> None:
        stack: list[TSNode] = [root]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                target = self._call_target(node, struct_name, receiver_types)
                if target is not None:
                    name, resolved = target
                    edges.append(
                        Edge(
                            source=caller_name,
                            target=name,
                            rel=RelType.CALLS,
                            metadata={} if resolved else {"unresolved": True},
                        )
                    )
            for child in node.children:
                if child.type != "function_declaration":
                    stack.append(child)

    def _call_target(
        self,
        call_node: TSNode,
        struct_name: str | None,
        receiver_types: dict[str, list[str]],
    ) -> tuple[str, bool] | None:
        """Resolve call target from a call_expression node."""
        # call_expression's first child is the function reference
        func = call_node.children[0] if call_node.children else None
        if func is None:
            return None

        if func.type == "identifier":
            name = _node_text(func)
            if name in _BUILTINS:
                return None
            return (name, False)

        if func.type == "field_expression":
            parts = self._field_expression_parts(func)
            if not parts:
                return None

            # self.method() -> StructName.method
            if parts[0] == "self" and struct_name and len(parts) == 2:
                return (f"{struct_name}.{parts[1]}", True)

            # receiver.method() where receiver came from Type.init() or an
            # explicit type annotation. Keep the target unresolved so the
            # scanner can bind module aliases and suffixes after all files load.
            if len(parts) == 2 and parts[0] in receiver_types:
                return (".".join([*receiver_types[parts[0]], parts[1]]), False)

            # Skip std.* calls
            if parts[0] == "std":
                return None

            return (".".join(parts), False)

        if func.type == "builtin_function":
            return None  # @import, @intCast, etc.

        return None

    def _field_expression_parts(self, node: TSNode) -> list[str]:
        """Flatten a.b.c field_expression to ['a', 'b', 'c']."""
        if node.type == "identifier":
            return [_node_text(node)]
        if node.type in ("pointer_type", "optional_type"):
            parts: list[str] = []
            for child in node.children:
                if child.is_named:
                    parts.extend(self._field_expression_parts(child))
            return parts
        if node.type == "field_expression":
            parts = []
            for child in node.children:
                if child.is_named:
                    parts.extend(self._field_expression_parts(child))
            return parts
        return []

    def _collect_receiver_types(self, body: TSNode) -> dict[str, list[str]]:
        receiver_types: dict[str, list[str]] = {}
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "variable_declaration":
                binding = self._receiver_binding(node)
                if binding is not None:
                    name, type_parts = binding
                    receiver_types[name] = type_parts
            for child in node.children:
                if child.type != "function_declaration":
                    stack.append(child)
        return receiver_types

    def _receiver_binding(self, node: TSNode) -> tuple[str, list[str]] | None:
        name_node = _variable_name_node(node)
        if name_node is None:
            return None
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            type_parts = self._field_expression_parts(type_node)
            if type_parts:
                return (_node_text(name_node), type_parts)

        initializer = _variable_initializer_node(node, name_node, type_node)
        if initializer is None:
            return None
        call = _unwrap_expression(initializer)
        if call is None or call.type != "call_expression" or not call.children:
            return None
        func = call.children[0]
        if func.type != "field_expression":
            return None
        parts = self._field_expression_parts(func)
        if len(parts) < 2 or parts[-1] not in _CONSTRUCTOR_FUNCTIONS:
            return None
        return (_node_text(name_node), parts[:-1])

    def _has_self_param(self, func_node: TSNode) -> bool:
        params = _find_child(func_node, "parameters")
        if params is None:
            return False
        for child in params.children:
            if child.type == "parameter":
                name = _find_child(child, "identifier")
                if name is not None and name.text == b"self":
                    return True
        return False


def _find_child(node: TSNode, type_name: str) -> TSNode | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _variable_name_node(node: TSNode) -> TSNode | None:
    for child in node.children:
        if child.type == "identifier":
            return child
    return None


def _variable_initializer_node(
    node: TSNode,
    name_node: TSNode,
    type_node: TSNode | None,
) -> TSNode | None:
    for child in reversed(node.children):
        if not child.is_named:
            continue
        if child == name_node or child == type_node:
            continue
        return child
    return None


def _unwrap_expression(node: TSNode) -> TSNode | None:
    current = node
    while current.type in ("try_expression", "catch_expression"):
        named_children = [child for child in current.children if child.is_named]
        if not named_children:
            return None
        current = named_children[0]
    return current


register(ZigExtractor())
