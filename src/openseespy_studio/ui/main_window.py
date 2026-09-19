        if not self._maybe_save_changes():
            return
        self.selection.clear()
        self.project = ProjectDatabase(
            name="Untitled",
            model=StructuralModel("Untitled"),
        )
        self.model = self.project.model
        self._project_path = None
        self._reset_runtime_results()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_dirty(False)
        self._refresh_all("New empty project")

    def _show_test_column_wizard(self) -> None:
        dialog = TestColumnWizard(
            self.project,
            parent=self,
        )
        if not dialog.exec():
            return

        before = self.project.to_dict()
        try:
            spec = dialog.data()
            for section in dialog.new_sections():
                self.project.add_section(section)

            if spec.replace_geometry:
                self.selection.clear()
                self._reset_runtime_results()

            result = build_test_column(
                self.project,
                spec,
            )
        except (KeyError, TypeError, ValueError) as exc:
            self.project = ProjectDatabase.from_dict(before)
            self.model = self.project.model
            QMessageBox.warning(
                self,
                "Quick 1D Column",
                str(exc),
            )
            self._refresh_all()
            return

        self.model = self.project.model
        extras = []
        if result.axial_pattern_tag is not None:
            extras.append(f"axial pattern {result.axial_pattern_tag}")
        if result.lateral_pattern_tag is not None:
            extras.append(
                f"lateral pattern {result.lateral_pattern_tag}"
            )
        if result.prescribed_pattern_tag is not None:
            extras.append(
                f"prescribed-displacement pattern "
                f"{result.prescribed_pattern_tag}"
            )
        if spec.top_mass > 0.0:
            extras.append("top mass")

        message = (
            f"Created 1D test column · {len(result.node_tags)} nodes · "
            f"{len(result.element_tags)} element(s) · "
            f"top node {result.top_node}"
        )