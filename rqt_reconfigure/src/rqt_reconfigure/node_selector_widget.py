# Software License Agreement (BSD License)
#
# Copyright (c) 2012, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: Isaac Saito

from __future__ import division

from collections import OrderedDict
import os
import sys
import cProfile

import dynamic_reconfigure as dyn_reconf
from python_qt_binding import loadUi
from python_qt_binding.QtCore import QRegExp, Qt, QTimer, Signal
from python_qt_binding.QtGui import QItemSelectionModel, QStandardItemModel, QWidget
import rospkg
import rospy
import rosservice

from .filter_children_model import FilterChildrenModel
from .parameter_item import ParameterItem
from .rqt_ros_graph import RqtRosGraph

class NodeSelectorWidget(QWidget):
    _COL_NAMES = ['Node']

    # public signal
    sig_node_selected = Signal(str)

    def __init__(self):
        super(NodeSelectorWidget, self).__init__()
        self.stretch = None

        rp = rospkg.RosPack()
        ui_file = os.path.join(rp.get_path('rqt_reconfigure'), 'resource',
                               'node_selector.ui')
        loadUi(ui_file, self)

        # List of the available nodes. Since the list should be updated over
        # time and we don't want to create node instance per every update cycle,
        # this list instance should better be capable of keeping track.
        self._nodeitems = OrderedDict()
        # self._nodeitems = {}
        # Dictionary. 1st elem is node's GRN name,
        # 2nd is ParameterItem instance.
        # TODO Needs updated when nodes list updated.

        #  Setup treeview and models
        self._std_model = QStandardItemModel()
        self._rootitem = self._std_model.invisibleRootItem()  # QStandardItem

        self._nodes_previous = None

        # Calling this method updates the list of the node.
        # Initially done only once.
#        rospy.loginfo('DEBUG before cprofile')
#        cProfile.runctx('self._update_nodetree()', globals(), locals())  #For debug. Needs to be removed
#        rospy.loginfo('DEBUG AFTER cprofile')
        self._update_nodetree()

        # TODO(Isaac): Needs auto-update function enabled, once another function
        #             that updates node tree with maintaining collapse/expansion
        #             state. http://goo.gl/GuwYp can be a help.

#        self.timer = QTimer()
#        self.timer.timeout.connect(self._refresh_nodes)
#        self.timer.start(5000) #  5sec interval is fast enough.

        self._collapse_button.pressed.connect(self._node_selector_view.collapseAll)
        self._expand_button.pressed.connect(self._node_selector_view.expandAll)
        
        # Filtering preparation.
        self._proxy_model = FilterChildrenModel()
        self._proxy_model.setDynamicSortFilter(True)
        self._proxy_model.setSourceModel(self._std_model)
        self._node_selector_view.setModel(self._proxy_model)

        # Setting slot for when user clicks on QTreeView.
        selectionModel = self._node_selector_view.selectionModel()
        selectionModel.selectionChanged.connect(self._selection_changed_slot)

    def _selection_changed_slot(self, selected, deselected):
        """
        Receives args from signal QItemSelectionModel.selectionChanged.
        
        :type selected: QItemSelection
        :type deselected: QItemSelection
        """
        
        selmodel = self._node_selector_view.selectionModel()

        index_current = selmodel.currentIndex()
        rospy.logdebug('_selection_changed_slot row=%d col=%d data=%s ' +
                       'data.parent=%s child(0, 0)=%s',
                       index_current.row(),
                       index_current.column(),
                       index_current.data(Qt.DisplayRole),
                       index_current.parent().data(Qt.DisplayRole),
                       index_current.child(0, 0).data(Qt.DisplayRole))

        if not index_current.child(0, 0).data(Qt.DisplayRole) == None:
            selmodel.select(index_current, QItemSelectionModel.Deselect)
            return  #  Meaning the selected is not the terminal node item. 

        # get the text of the selected item
        node_name_selected = RqtRosGraph.get_upper_grn(index_current, '')
        
        rospy.logdebug('_selection_changed_slot node_name_selected=%s',
                       node_name_selected)
        self.sig_node_selected.emit(node_name_selected)
        
        # Show the node as selected.
        #selmodel.select(index_current, QItemSelectionModel.SelectCurrent)

    def get_paramitems(self):
        """
        :rtype: OrderedDict 1st elem is node's GRN name, 
                2nd is ParameterItem instance
        """
        return self._nodeitems

    def _update_nodetree(self):
        """
        """

        # TODO(Isaac): 11/25/2012 dynamic_reconfigure only returns params that
        #             are associated with nodes. In order to handle independent
        #             params, different approach needs taken.
        try:
            nodes = dyn_reconf.find_reconfigure_services()
        except rosservice.ROSServiceIOException as e:
            rospy.logerr("Reconfigure GUI cannot connect to master.")
            raise e  # TODO Make sure 'raise' here returns or finalizes this func.

        if not nodes == self._nodes_previous:
            paramname_prev = ''
            paramitem_top_prev = None
            i_node_curr = 1
            num_nodes = len(nodes)
            for node_name_grn in nodes:

                ####(Begin) For DEBUG ONLY; skip some dynreconf creation
#                if i_node_curr % 5 != 0:
#                    i_node_curr += 1
#                    continue
                #### (End) For DEBUG ONLY. ####

                # Please don't remove - this is not a debug print.
                rospy.loginfo('rqt_reconfigure loading #{}/{} node={}'.format(
                                        i_node_curr, num_nodes, node_name_grn))

                paramitem_full_nodename = ParameterItem(
                                     node_name_grn, ParameterItem.NODE_FULLPATH)
                #paramitem_full_nodename.set_param_name(node_name_grn)
                names = paramitem_full_nodename.get_param_names()

                # paramitem_full_nodename is the node that represents node.
                # self._nodeitems.append(paramitem_full_nodename)
                self._nodeitems[node_name_grn] = paramitem_full_nodename

                i_node_curr += 1
                rospy.logdebug('_update_nodetree i=%d names=%s',
                               i_node_curr, names)

                self._add_tree_node(paramitem_full_nodename,
                                    self._rootitem,
                                    names)

    def _add_tree_node(self, param_item_full, stditem_parent, child_names_left):
        """
        
        Evaluate current treenode and the previous treenode at the same depth.
        If the name of both nodes is the same, current node instance is ignored.
        If not, the current node gets added to the same parent node.
        At the end, this function gets called recursively going down 1 level.
        
        :type param_item_full: ParameterItem
        :type stditem_parent: QStandardItem.
        :type child_names_left: List of str
        :param child_names_left: List of strings that is sorted in hierarchical 
                                 order of params.
        """
        # TODO(Isaac): Consider moving to rqt_py_common.

        name_curr = child_names_left.pop(0)
        stditem_curr = ParameterItem(param_item_full.get_raw_param_name())

        # item at the bottom is your most recent node.
        row_index_parent = stditem_parent.rowCount() - 1

        # Obtain and instantiate prev node in the same depth.
        name_prev = ''
        stditem_prev = None
        if not stditem_parent.child(row_index_parent) == None:
            stditem_prev = stditem_parent.child(row_index_parent)
            name_prev = stditem_prev.text()

        stditem = None
        if name_prev != name_curr:
            stditem_curr.setText(name_curr)
            stditem_parent.appendRow(stditem_curr)
            stditem = stditem_curr
        else:
            stditem = stditem_prev

        rospy.logdebug('add_tree_node 1 name_curr=%s ' +
                       '\n\t\t\t\t\tname_prev=%s row_index_parent=%d',
                       name_curr, name_prev, row_index_parent)

        if len(child_names_left) != 0:
            # TODO: View & Model are closely bound here. Ideally isolate this 2.
            #       Maybe we should split into 2 classs, 1 handles view,
            #       the other does model.
            self._add_tree_node(param_item_full, stditem, child_names_left)

    def _refresh_nodes(self):
        # TODO(Isaac) In the future, do NOT remove all nodes. Instead,
        #            remove only the ones that are gone. And add new ones too.

        model = self._rootitem
        if model.hasChildren():
            row_count = model.rowCount()
            model.removeRows(0, row_count)
            rospy.logdebug("ParamWidget _refresh_nodes row_count=%s", row_count)
        self._update_nodetree()

    def close_node(self):
        rospy.logdebug(" in close_node")
        # TODO(Isaac) Figure out if dynamic_reconfigure needs to be closed.
        
    def filter_key_changed(self, text):
        """
        Slot that accepts filtering key.
        
        Taken from example:
        http://doc.qt.digia.com/qt/itemviews-basicsortfiltermodel.html
        """
        
        # Other than RegEx, Wild card, Fixed text are also possible. Right now
        # RegEx is in use in hope of it works the best.
        syntax_nr = QRegExp.RegExp 
        
        syntax = QRegExp.PatternSyntax(syntax_nr)
        regExp = QRegExp(text, Qt.CaseInsensitive, syntax)
        self._proxy_model.setFilterRegExp(regExp)        
