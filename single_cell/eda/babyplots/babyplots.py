"""Python API for the babyplots plotting library.

With this package, you can create babyplots visualizations in a Jupyter
notebook to easily explore and present 3-dimensional data.

Please find the complete documentation at:
https://bp.bleb.li/documentation/python
"""

import os
from functools import reduce
from typing import Union, List
from uuid import uuid4
import json

import numpy as np
from skimage import io
from skimage.util import img_as_float
from IPython.display import HTML, Javascript, display
import jinja2


dirname = os.path.dirname(
    os.path.realpath(__file__)
)

t_loader = jinja2.FileSystemLoader(os.path.join(dirname, 'templates'))
JENV = jinja2.Environment(loader=t_loader)


def _snakecase2camelcase(name: str):
    """
    Example:
        >>> _snakecase2camelcase('point_cloud')
        'pointCloud'
    """
    if not name.islower():
        raise ValueError('snake_case should be used instead of CamelCase.')
    if name == 'heatmap':
        return 'heatMap'
    return ''.join(i.capitalize() if idx else i for idx, i in enumerate(name.split('_')))


class Babyplot(object):
    """The Babyplot class stores the individual plots of the visualization and
    their options.

    The first step to create a babyplots visualization is to create a Babyplot
    object. Then you can use its methods to add plots and display them.

    """
    # _plot_type_map = dict(
    #     point_cloud='pointCloud',
    #     shape_cloud='shapeCloud',
    #     heatmap='heatMap',
    #     surface='surface'
    # )
    # _options_map = dict(
    #     name='name',
    #     color_scale='colorScale',
    #     custom_color_scale='customColorScale',
    #     color_scale_inverted='colorScaleInverted',
    #     sorted_categories='sortedCategories',
    #     show_legend='showLegend',
    #     legend_show_shape
    # )

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        background_color: str = "#ffffffff",
        turntable: bool = False,
        rotation_rate: float = 0.01,
        x_scale: float = 1,
        y_scale: float = 1,
        z_scale: float = 1,
        shape_legend_title: str = "",
        show_ui: bool = False
    ):
        """
        Parameters
        ---
        width: Width of the visualization.

        height: Height of the visualization.

        background_color: Background color of the visualization in hex format
        (e.g. "#ffffffff).

        turntable: Setting turntable to True spins the camera around the plots
        at a constant speed.

        rotation_rate: The speed at which the camera turns around the plots if
        turntable is set to True.

        x_scale: Apply a scaling factor to the x axis.

        y_scale: Apply a scaling factor to the y axis.

        z_scale: Apply a scaling factor to the z axis.

        shape_legend_title: Title of the legend showing the names and plot
        types of multiple plots, if at least one plot has legendShowShape
        enabled.

        show_ui: Display control buttons on the visualization that allow
        annotating the plot with labels, exporting the plot as a .json file and
        publishing the plot to https://bp.bleb.li.

        """
        self.plots = []
        self.turntable = turntable
        self.rotation_rate = rotation_rate
        self.width = width
        self.height = height
        self.background_color = background_color
        self.x_scale = x_scale
        self.y_scale = y_scale
        self.z_scale = z_scale
        self.shape_legend_title = shape_legend_title
        self.show_ui = show_ui
        bpjs_file = os.path.join(
            dirname,
            'js/babyplots.js'
        )
        with open(bpjs_file, 'r', encoding="utf-8") as infile:
            bpjs = infile.read()
        bpjs = "define('Baby', [], function() {{{0}\nreturn Baby;}})".format(
            bpjs)
        display(Javascript(bpjs))

    @staticmethod
    def format_json(prop: any) -> str:
        return json.dumps(prop)

    def add_plot(
            self,
            coordinates: List[List[float]],
            plot_type: str,
            color_by: str,
            color_var: Union[List[float], List[str]],
            options: dict = {}
    ):
        """Add a plot to the Babyplot object

        Parameters
        ---
        coordinates: The coordinates of the data points.

        plot_tyes: Either "pointCloud", "shapeCloud", "heatMap", or "surface".

        color_by: Either "categories", "values", or "direct".

        color_var: The variable to use for coloring the data points; Either a
        list of discrete categories, numerical values, or colors in hex format
        (e.g. "#ff0000").

        options: A dictionary of plot options. Please refer to the
        documentation (https://bp.bleb.li/documentation/python") for a complete
        list of possible options.

        """
        

        if isinstance(coordinates, np.ndarray):
            coordinates = coordinates.tolist()
        if isinstance(color_var, np.ndarray):
            color_var = color_var.tolist()
        embedding = options.get('folded_embedding')
        if isinstance(embedding, np.ndarray):
            options['folded_embedding'] = embedding.tolist()
        plot_type = _snakecase2camelcase(plot_type)
        options = {_snakecase2camelcase(k): v for k, v in options.items()}


        self.plots.append(
            {
                'coordinates': coordinates,
                'plot_type': plot_type,
                'color_by': color_by,
                'color_var': color_var,
                'options': options
            }
        )
        return self

    def add_img_stack(
            self,
            values: List[float],
            indices: List[int],
            attributes: dict,
            options: dict = {}
    ):
        """Add an image stack visualization to the Babyplot object.

        Expects the image to be in a special format optimized for small size in
        json. Use the add_tiff() method to add an image directly.

        Parameters
        ---
        values: A list of pixel intensities at the image pixels given by the
        indices parameter.

        indices: A list of indices of included pixels. Used to reconstruct the
        3d image. The order of the pixels is: Z, C, Y, X

        attributes: A dictionary with image attributes. Must at least have the
        "dim" key, giving the dimensions of the 3d image stack.

        options: A dictionary of visualization options. Please refer to the
        documentation (https://bp.bleb.li/documentation/python") for a complete
        list of possible options.

        """
        self.plots.append(
            {
                'plot_type': "imageStack",
                'values': values,
                'indices': indices,
                'attributes': attributes,
                'options': options
            }
        )

    def add_tiff(
        self,
        image_path: str,
        threshold: float = 0.1,
        channel_thresholds: List[float] = None,
        options: dict = {}
    ):
        """Add a 3d image stack from a tiff file to the Babyplot object.

        Parameters
        ---
        image_path: File path of the tiff image stack.

        threshold: A global threshold for all color channels.

        channel_thresholds: A list of individual thresholds for each channel.

        options: A dictionary of visualization options. Please refer to the
        documentation (https://bp.bleb.li/documentation/python") for a complete
        list of possible options.

        """
        im = img_as_float(io.imread(image_path))  # im shape: z, x, y, c
        # if image has no color channels, adjust dimensions
        if len(im.shape) == 3:
            im = np.expand_dims(im, axis=-1)
        # set shape attribute
        attributes = {
            "dim": [im.shape[1], im.shape[2], im.shape[3], im.shape[0]]
        }
        # apply channel-wise thresholds if given.
        if channel_thresholds is not None:
            for i, thres in enumerate(channel_thresholds):
                mask = im[:, :, :, i] < thres
                im[:, :, :, i][mask] = 0
        # reorder dimensions to that flatten gives the same order as R equivalent
        im = np.transpose(im, (0, 3, 2, 1))  # im shape becomes z, c, y, x
        # flatten
        n_vals = reduce(lambda x, y: x*y, im.shape)
        im = np.reshape(im, n_vals)
        # find indices of values larger than threshold
        # single threshold is ignored when per channel thresholds are given
        if channel_thresholds is None:
            idcs = np.argwhere(im > threshold).squeeze()
        else:
            idcs = np.argwhere(im > 0).squeeze()
        # only keep non-zero values
        im = im[idcs].tolist()
        idcs = idcs.tolist()

        self.add_img_stack(im, idcs, attributes, options)

    def _repr_html_(self):
        """Displays the babyplots visualization in a Jupyter Notebook."""
        display_id = str(uuid4()).replace('-', '_')

        html = JENV.get_template('plot.html')
        output = html.render(baby=self, display_id=display_id)
        return output

    def as_html(
        self,
        standalone: bool = True,
        fullscreen: bool = False,
        title: str = "Babyplot"
    ) -> str:
        """Returns the babyplots visualization as an html string.

        Parameters
        ---
        standalone: If True, the returned string is a complete html document,
        if False, only the canvas and the plot data.

        fullscreen: If set to True, the visualization will fill the viewport,
        if not, it will conform to the dimensions set in the Babyplot object.

        title: Title of the html page.

        """
        display_id = str(uuid4()).replace('-', '_')
        bpjs_file = os.path.join(
            dirname,
            'js/babyplots.js'
        )
        with open(bpjs_file, 'r', encoding="utf-8") as infile:
            bpjs = infile.read()
        html = JENV.get_template('save_plot.html')
        output = html.render(
            baby=self,
            standalone=standalone,
            display_id=display_id,
            bpjs=bpjs,
            vis_name=title,
            fullscreen=fullscreen
        )
        return output

    def save_as_html(
        self,
        path: str,
        fullscreen: bool = False,
        title: str = "Babyplot"
    ):
        """Save the babyplots visualization as an html file.

        Parameters
        ---
        path: Filepath for the output.

        fullscreen: If set to True, the visualization will fill the viewport,
        if not, it will conform to the dimensions set in the Babyplot object.

        title: Title of the html page.

        """
        with open(path, "w", encoding="utf-8") as outfile:
            outfile.write(self.as_html(True, fullscreen, title))
