$(document).ready(function() {
  $('#dataTable2').DataTable({
    ajax: {url: "/admin-api/get-table-data-2",
    type: "GET",
    dataSrc: ''
  },
    columns: [
      {data: "Name"},
      {data: "Heart_Rate"},
      {data: "Temperature"},
      {data: "Humidity"}
    ]
  });
});
