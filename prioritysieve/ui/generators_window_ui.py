from PyQt6 import QtCore, QtWidgets


class Ui_GeneratorsWindow(object):
    def setupUi(self, GeneratorsWindow):
        GeneratorsWindow.setObjectName("GeneratorsWindow")
        GeneratorsWindow.resize(960, 640)
        self.centralwidget = QtWidgets.QWidget(parent=GeneratorsWindow)
        self.centralwidget.setObjectName("centralwidget")

        self.verticalLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName("verticalLayout")

        self.inputGroupBox = QtWidgets.QGroupBox(parent=self.centralwidget)
        self.inputGroupBox.setObjectName("inputGroupBox")
        self.inputGroupLayout = QtWidgets.QVBoxLayout(self.inputGroupBox)
        self.inputGroupLayout.setObjectName("inputGroupLayout")

        self.inputDirLayout = QtWidgets.QHBoxLayout()
        self.inputDirLayout.setObjectName("inputDirLayout")
        self.selectFolderPushButton = QtWidgets.QPushButton(parent=self.inputGroupBox)
        self.selectFolderPushButton.setObjectName("selectFolderPushButton")
        self.inputDirLayout.addWidget(self.selectFolderPushButton)
        self.inputDirLineEdit = QtWidgets.QLineEdit(parent=self.inputGroupBox)
        self.inputDirLineEdit.setObjectName("inputDirLineEdit")
        self.inputDirLayout.addWidget(self.inputDirLineEdit)
        self.inputGroupLayout.addLayout(self.inputDirLayout)

        self.verticalLayout.addWidget(self.inputGroupBox)

        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.buttonLayout.setObjectName("buttonLayout")
        spacer_left = QtWidgets.QSpacerItem(
            40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum
        )
        self.buttonLayout.addItem(spacer_left)
        self.loadFilesPushButton = QtWidgets.QPushButton(parent=self.centralwidget)
        self.loadFilesPushButton.setObjectName("loadFilesPushButton")
        self.buttonLayout.addWidget(self.loadFilesPushButton)
        self.viewReportPushButton = QtWidgets.QPushButton(parent=self.centralwidget)
        self.viewReportPushButton.setObjectName("viewReportPushButton")
        self.buttonLayout.addWidget(self.viewReportPushButton)
        self.generatePriorityFilePushButton = QtWidgets.QPushButton(parent=self.centralwidget)
        self.generatePriorityFilePushButton.setObjectName("generatePriorityFilePushButton")
        self.buttonLayout.addWidget(self.generatePriorityFilePushButton)
        self.generateStudyPlanPushButton = QtWidgets.QPushButton(parent=self.centralwidget)
        self.generateStudyPlanPushButton.setObjectName("generateStudyPlanPushButton")
        self.buttonLayout.addWidget(self.generateStudyPlanPushButton)
        spacer_right = QtWidgets.QSpacerItem(
            40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum
        )
        self.buttonLayout.addItem(spacer_right)
        self.verticalLayout.addLayout(self.buttonLayout)

        self.tablesTabWidget = QtWidgets.QTabWidget(parent=self.centralwidget)
        self.tablesTabWidget.setObjectName("tablesTabWidget")

        self.tabCounts = QtWidgets.QWidget()
        self.tabCounts.setObjectName("tabCounts")
        self.countsLayout = QtWidgets.QVBoxLayout(self.tabCounts)
        self.countsLayout.setObjectName("countsLayout")
        self.numericalTableWidget = QtWidgets.QTableWidget(parent=self.tabCounts)
        self.numericalTableWidget.setObjectName("numericalTableWidget")
        self.numericalTableWidget.setColumnCount(7)
        self.numericalTableWidget.setRowCount(0)
        for index in range(7):
            item = QtWidgets.QTableWidgetItem()
            self.numericalTableWidget.setHorizontalHeaderItem(index, item)
        self.numericalTableWidget.horizontalHeader().setStretchLastSection(True)
        self.countsLayout.addWidget(self.numericalTableWidget)
        self.tablesTabWidget.addTab(self.tabCounts, "")

        self.tabPercents = QtWidgets.QWidget()
        self.tabPercents.setObjectName("tabPercents")
        self.percentsLayout = QtWidgets.QVBoxLayout(self.tabPercents)
        self.percentsLayout.setObjectName("percentsLayout")
        self.percentTableWidget = QtWidgets.QTableWidget(parent=self.tabPercents)
        self.percentTableWidget.setObjectName("percentTableWidget")
        self.percentTableWidget.setColumnCount(5)
        self.percentTableWidget.setRowCount(0)
        for index in range(5):
            item = QtWidgets.QTableWidgetItem()
            self.percentTableWidget.setHorizontalHeaderItem(index, item)
        self.percentTableWidget.horizontalHeader().setStretchLastSection(True)
        self.percentsLayout.addWidget(self.percentTableWidget)
        self.tablesTabWidget.addTab(self.tabPercents, "")

        self.verticalLayout.addWidget(self.tablesTabWidget)

        GeneratorsWindow.setCentralWidget(self.centralwidget)
        self.retranslateUi(GeneratorsWindow)
        self.tablesTabWidget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(GeneratorsWindow)

    def retranslateUi(self, GeneratorsWindow):
        _translate = QtCore.QCoreApplication.translate
        GeneratorsWindow.setWindowTitle(_translate("GeneratorsWindow", "PrioritySieve Generators"))
        self.inputGroupBox.setTitle(_translate("GeneratorsWindow", "Input"))
        self.selectFolderPushButton.setText(_translate("GeneratorsWindow", "Choose Folder"))
        self.loadFilesPushButton.setText(_translate("GeneratorsWindow", "Load Files"))
        self.viewReportPushButton.setText(_translate("GeneratorsWindow", "Readability Report"))
        self.generatePriorityFilePushButton.setText(_translate("GeneratorsWindow", "Generate Priority File"))
        self.generateStudyPlanPushButton.setText(_translate("GeneratorsWindow", "Generate Study Plan"))
        self.tablesTabWidget.setTabText(
            self.tablesTabWidget.indexOf(self.tabCounts),
            _translate("GeneratorsWindow", "Counts"),
        )
        self.tablesTabWidget.setTabText(
            self.tablesTabWidget.indexOf(self.tabPercents),
            _translate("GeneratorsWindow", "Percentages"),
        )

        headers_counts = [
            _translate("GeneratorsWindow", "File"),
            _translate("GeneratorsWindow", "Unique entries"),
            _translate("GeneratorsWindow", "Reviewed entries"),
            _translate("GeneratorsWindow", "Unreviewed entries"),
            _translate("GeneratorsWindow", "Total occurrences"),
            _translate("GeneratorsWindow", "Reviewed occurrences"),
            _translate("GeneratorsWindow", "Unreviewed occurrences"),
        ]
        for index, label in enumerate(headers_counts):
            item = self.numericalTableWidget.horizontalHeaderItem(index)
            if item is not None:
                item.setText(label)

        headers_percents = [
            _translate("GeneratorsWindow", "File"),
            _translate("GeneratorsWindow", "Reviewed entries %"),
            _translate("GeneratorsWindow", "Unreviewed entries %"),
            _translate("GeneratorsWindow", "Reviewed occurrences %"),
            _translate("GeneratorsWindow", "Unreviewed occurrences %"),
        ]
        for index, label in enumerate(headers_percents):
            item = self.percentTableWidget.horizontalHeaderItem(index)
            if item is not None:
                item.setText(label)
