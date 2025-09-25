# Form implementation generated from reading ui file 'ankimorphs/ui/sudachi_manager_dialog.ui'
#
# Created by: manual conversion for AnkiMorphs
#
# WARNING: Any manual changes made to this file should keep UI in sync with the .ui source.

from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_SudachiManagerDialog(object):
    def setupUi(self, SudachiManagerDialog):
        SudachiManagerDialog.setObjectName("SudachiManagerDialog")
        SudachiManagerDialog.resize(520, 360)
        self.verticalLayout = QtWidgets.QVBoxLayout(SudachiManagerDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.installSudachiButton = QtWidgets.QPushButton(parent=SudachiManagerDialog)
        self.installSudachiButton.setObjectName("installSudachiButton")
        self.horizontalLayout.addWidget(self.installSudachiButton)
        self.sudachiStatusLabel = QtWidgets.QLabel(parent=SudachiManagerDialog)
        font = QtGui.QFont()
        font.setItalic(True)
        self.sudachiStatusLabel.setFont(font)
        self.sudachiStatusLabel.setObjectName("sudachiStatusLabel")
        self.horizontalLayout.addWidget(self.sudachiStatusLabel)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.removeSudachiButton = QtWidgets.QPushButton(parent=SudachiManagerDialog)
        self.removeSudachiButton.setObjectName("removeSudachiButton")
        self.horizontalLayout.addWidget(self.removeSudachiButton)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.dictionariesListWidget = QtWidgets.QListWidget(parent=SudachiManagerDialog)
        self.dictionariesListWidget.setObjectName("dictionariesListWidget")
        self.horizontalLayout_2.addWidget(self.dictionariesListWidget)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.verticalLayout_2.addItem(spacerItem1)
        self.installDictionaryButton = QtWidgets.QPushButton(parent=SudachiManagerDialog)
        self.installDictionaryButton.setObjectName("installDictionaryButton")
        self.verticalLayout_2.addWidget(self.installDictionaryButton)
        self.removeDictionaryButton = QtWidgets.QPushButton(parent=SudachiManagerDialog)
        self.removeDictionaryButton.setObjectName("removeDictionaryButton")
        self.verticalLayout_2.addWidget(self.removeDictionaryButton)
        spacerItem2 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.verticalLayout_2.addItem(spacerItem2)
        self.horizontalLayout_2.addLayout(self.verticalLayout_2)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.infoLabel = QtWidgets.QLabel(parent=SudachiManagerDialog)
        self.infoLabel.setWordWrap(True)
        self.infoLabel.setObjectName("infoLabel")
        self.verticalLayout.addWidget(self.infoLabel)

        self.retranslateUi(SudachiManagerDialog)
        QtCore.QMetaObject.connectSlotsByName(SudachiManagerDialog)

    def retranslateUi(self, SudachiManagerDialog):
        _translate = QtCore.QCoreApplication.translate
        SudachiManagerDialog.setWindowTitle(_translate("SudachiManagerDialog", "Sudachi Manager"))
        self.installSudachiButton.setText(_translate("SudachiManagerDialog", "Install SudachiPy"))
        self.sudachiStatusLabel.setText(_translate("SudachiManagerDialog", "SudachiPy is not installed."))
        self.removeSudachiButton.setText(_translate("SudachiManagerDialog", "Remove SudachiPy"))
        self.installDictionaryButton.setText(_translate("SudachiManagerDialog", "Install Dictionary"))
        self.removeDictionaryButton.setText(_translate("SudachiManagerDialog", "Remove Dictionary"))
        self.infoLabel.setText(_translate("SudachiManagerDialog", "Install SudachiPy and optionally download one of the supported dictionaries. Each installed dictionary appears as its own morphemizer in the AnkiMorphs Note Filter settings."))
