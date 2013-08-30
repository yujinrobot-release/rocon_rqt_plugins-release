#!/usr/bin/env python
#
# License: BSD
#   https://raw.github.com/robotics-in-concert/rocon_multimaster/master/rocon_gateway_graph/LICENSE
#
##############################################################################
# Imports
##############################################################################

from __future__ import division
import os

from python_qt_binding import loadUi
from python_qt_binding.QtCore import QFile, QIODevice, Qt, Signal, QAbstractListModel, pyqtSignal
from python_qt_binding.QtGui import QFileDialog, QGraphicsScene, QIcon, QImage, QPainter, QWidget, QCompleter, QBrush, QColor, QPen, QPushButton, QTabWidget, QPlainTextEdit,QGridLayout, QVBoxLayout, QHBoxLayout
from python_qt_binding.QtSvg import QSvgGenerator

import rosgraph.impl.graph
import rosservice
import rostopic
import rospkg

######################
#dwlee
import rosnode
import roslib
import rospy
from concert_msgs.msg import ConcertClients
###########################

from .dotcode import RosGraphDotcodeGenerator
from .interactive_graphics_view import InteractiveGraphicsView
from qt_dotgraph.dot_to_qt import DotToQtGenerator
from qt_gui.plugin import Plugin

# pydot requires some hacks
from qt_dotgraph.pydotfactory import PydotFactory
# TODO: use pygraphviz instead, but non-deterministic layout will first be resolved in graphviz 2.30
# from qtgui_plugin.pygraphvizfactory import PygraphvizFactory

from rocon_gateway import Graph
from conductor_graph_info import ConductorGraphInfo



##############################################################################
# Utility Classes
##############################################################################


class RepeatedWordCompleter(QCompleter):
    """A completer that completes multiple times from a list"""

    def init(self, parent=None):
        QCompleter.init(self, parent)

    def pathFromIndex(self, index):
        path = QCompleter.pathFromIndex(self, index)
        lst = str(self.widget().text()).split(',')
        if len(lst) > 1:
            path = '%s, %s' % (','.join(lst[:-1]), path)
        return path

    def splitPath(self, path):
        path = str(path.split(',')[-1]).lstrip(' ')
        return [path]


class NodeEventHandler():
    def __init__(self,tabWidget,node_item,callback_func):
        self._tabWidget = tabWidget
        self._callback_func = callback_func
        self._node_item = node_item


    def NodeEvent(self,event):
        for k in range(self._tabWidget.count()):
             if self._tabWidget.tabText(k) == self._node_item._label.text():
                self._tabWidget.setCurrentIndex (k)
 
        
class NamespaceCompletionModel(QAbstractListModel):
    """Ros package and stacknames"""
    def __init__(self, linewidget, topics_only):
        super(QAbstractListModel, self).__init__(linewidget)
        self.names = []

    def refresh(self, names):
        namesset = set()
        for n in names:
            namesset.add(str(n).strip())
            namesset.add("-%s" % (str(n).strip()))
        self.names = sorted(namesset)

    def rowCount(self, parent):
        return len(self.names)

    def data(self, index, role):
        if index.isValid() and (role == Qt.DisplayRole or role == Qt.EditRole):
            return self.names[index.row()]
        return None

##############################################################################
# Gateway Classes
##############################################################################


class ConductorGraph(Plugin):

    _deferred_fit_in_view = Signal()
    _client_list_update_signal = Signal()
    
    def __init__(self, context):
        self._context = context
        super(ConductorGraph, self).__init__(context)
        self.initialised = False
        self.setObjectName('Conductor Graph')
        self._current_dotcode = None
        
        self._node_item_events = {}
        self._client_info_list = {}
        self._widget = QWidget()
        

        # factory builds generic dotcode items
        self.dotcode_factory = PydotFactory()
        # self.dotcode_factory = PygraphvizFactory()
        self.dotcode_generator = RosGraphDotcodeGenerator()
        self.dot_to_qt = DotToQtGenerator()
        self._graph = ConductorGraphInfo()

        rospack = rospkg.RosPack()
        ui_file = os.path.join(rospack.get_path('rocon_conductor_graph'), 'ui', 'conductor_graph.ui')
        #ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ui', 'conductor_graph.ui')
        loadUi(ui_file, self._widget, {'InteractiveGraphicsView': InteractiveGraphicsView})
        self._widget.setObjectName('ConductorGraphUi')

        if context.serial_number() > 1:
            self._widget.setWindowTitle(self._widget.windowTitle() + (' (%d)' % context.serial_number()))

        self._scene = QGraphicsScene()
        self._scene.setBackgroundBrush(Qt.white)
        self._widget.graphics_view.setScene(self._scene)

        self._widget.refresh_graph_push_button.setIcon(QIcon.fromTheme('view-refresh'))
        self._widget.refresh_graph_push_button.pressed.connect(self._update_conductor_graph)

        self._widget.highlight_connections_check_box.toggled.connect(self._redraw_graph_view)
        self._widget.auto_fit_graph_check_box.toggled.connect(self._redraw_graph_view)
        self._widget.fit_in_view_push_button.setIcon(QIcon.fromTheme('zoom-original'))
        self._widget.fit_in_view_push_button.pressed.connect(self._fit_in_view)

        self._update_conductor_graph()
        self._deferred_fit_in_view.connect(self._fit_in_view, Qt.QueuedConnection)
        self._deferred_fit_in_view.emit()
        
        #add by dwlee
        self._client_list_update_signal.connect(self._update_conductor_graph)
        rospy.Subscriber("/concert/list_concert_clients", ConcertClients, self._update_client_list)

        context.add_widget(self._widget)
  
    def restore_settings(self, plugin_settings, instance_settings):
        self.initialised = True
        self._refresh_rosgraph()

    def shutdown_plugin(self):
        pass

    def _update_conductor_graph(self):
        # re-enable controls customizing fetched ROS graph

        self._graph.update()
        self._refresh_rosgraph()
        self._update_client_tab()

    def _refresh_rosgraph(self):
        if not self.initialised:
            return
        self._update_graph_view(self._generate_dotcode())
        
    def _generate_dotcode(self):
        return self.dotcode_generator.generate_dotcode(rosgraphinst=self._graph,
                                                       dotcode_factory=self.dotcode_factory,
                                                       orientation='LR'
                                                       )
    def _update_graph_view(self, dotcode): 
        if dotcode == self._current_dotcode:
            return
        self._current_dotcode = dotcode
        self._redraw_graph_view()
   
    def _update_client_list(self,data):
        self._client_list_update_signal.emit()
        pass
    
    def _start_service(self,node_name,service_name):
        print node_name+":\n "+service_name
            
    def _update_client_tab(self):
        self._widget.tabWidget.clear()    
        for k in self._graph._client_info_list.values(): 
            main_widget=QWidget()
           
            ver_layout = QVBoxLayout(main_widget)
            ver_layout.setContentsMargins (9,9,9,9)
            ver_layout.setSizeConstraint (ver_layout.SetDefaultConstraint)
            
            sub_widget = QWidget()
            btn_grid_layout = QGridLayout(sub_widget)
            btn_grid_layout.setContentsMargins (9,9,9,9)

            btn_grid_layout.setColumnStretch (1, 0)
            btn_grid_layout.setRowStretch (2, 0)

            btn_invite = QPushButton("invite")
            btn_list_apps = QPushButton("list_apps")
            btn_platform_info = QPushButton("platform_info")
            btn_status = QPushButton("status")
            btn_start_app = QPushButton("start_app")
            btn_stop_app = QPushButton("stop_app")            

            btn_invite.clicked.connect(lambda: self._start_service(self._widget.tabWidget.tabText(self._widget.tabWidget.currentIndex()),"invite"))
            btn_list_apps.clicked.connect(lambda: self._start_service(self._widget.tabWidget.tabText(self._widget.tabWidget.currentIndex()),"list_apps"))  
            btn_platform_info.clicked.connect(lambda: self._start_service(self._widget.tabWidget.tabText(self._widget.tabWidget.currentIndex()),"platform_info"))  
            btn_status.clicked.connect(lambda: self._start_service(self._widget.tabWidget.tabText(self._widget.tabWidget.currentIndex()),"status"))  
            btn_start_app.clicked.connect(lambda: self._start_service(self._widget.tabWidget.tabText(self._widget.tabWidget.currentIndex()),"start_app"))  
            btn_stop_app.clicked.connect(lambda: self._start_service(self._widget.tabWidget.tabText(self._widget.tabWidget.currentIndex()),"stop_app"))  
                    
            btn_grid_layout.addWidget(btn_invite)
            btn_grid_layout.addWidget(btn_list_apps)
            btn_grid_layout.addWidget(btn_platform_info)
            btn_grid_layout.addWidget(btn_status)
            btn_grid_layout.addWidget(btn_start_app)
            btn_grid_layout.addWidget(btn_stop_app)
             
            ver_layout.addWidget(sub_widget)            
            
            text_widget = QPlainTextEdit()
            text_widget.appendHtml(k["tab_context"])
            ver_layout.addWidget(text_widget)
            
            self._widget.tabWidget.addTab(main_widget, k["tab_name"]);
        
    def _redraw_graph_view(self):
        self._scene.clear()
        self._node_item_events = {}

        if self._widget.highlight_connections_check_box.isChecked():
            highlight_level = 3
        else:
            highlight_level = 1

        # layout graph and create qt items
        (nodes, edges) = self.dot_to_qt.dotcode_to_qt_items(self._current_dotcode,
                                                            highlight_level=highlight_level,
                                                            same_label_siblings=True)
        # if we wish to make special nodes, do that here (maybe subclass GraphItem, just like NodeItem does)
        #node
        for node_item in nodes.itervalues():
            # set the color of conductor to orange           
            if node_item._label.text() == self._graph._concert_conductor_name:
                royal_blue = QColor(65, 105, 255)
                node_item._default_color = royal_blue
                node_item.set_color(royal_blue)
          
            # redefine mouse event
            self._node_item_events[node_item._label.text()] = NodeEventHandler(self._widget.tabWidget,node_item,node_item.mouseDoubleClickEvent);
            node_item.mouseDoubleClickEvent = self._node_item_events[node_item._label.text()].NodeEvent;
            
            self._scene.addItem(node_item)
            
        #edge
        for edge_items in edges.itervalues():
            for edge_item in edge_items:
                edge_item.add_to_scene(self._scene)
                 #set the color of node as connection strength one of red, yellow, green
                edge_dst_name = edge_item.to_node._label.text()
                if self._graph._client_info_list.has_key(edge_dst_name):   
                  connection_strength = self._graph._client_info_list[edge_dst_name]['connection_strength']
                  if connection_strength == 'very_strong':
                      green = QColor(0, 255, 0)
                      edge_item._default_color = green
                      edge_item.set_color(green)

                  elif connection_strength == 'strong':
                      green_yellow = QColor(125, 255,0)
                      edge_item._default_color = green_yellow
                      edge_item.set_color(green_yellow)
                        
                  elif connection_strength == 'normal':
                      yellow = QColor(238, 238,0)
                      edge_item._default_color = yellow
                      edge_item.set_color(yellow)

                  elif connection_strength == 'weak':
                      yellow_red = QColor(255, 125,0)
                      edge_item._default_color = yellow_red
                      edge_item.set_color(yellow_red)
                      
                  elif connection_strength == 'very_weak':
                      red = QColor(255, 0,0)
                      edge_item._default_color = red
                      edge_item.set_color(red)
    
        self._scene.setSceneRect(self._scene.itemsBoundingRect())
  
        if self._widget.auto_fit_graph_check_box.isChecked():
            self._fit_in_view()

    def _fit_in_view(self):
        self._widget.graphics_view.fitInView(self._scene.itemsBoundingRect(), Qt.KeepAspectRatio)

